import logging
import os
import shutil
import tempfile
import zipfile

import azure.functions as func
import pandas as pd

from shared.db import (
    get_connection,
    get_latest_recorded_at,
    insert_price_history_delta,
    log_run,
    upsert_stations,
)

KAGGLE_DATASET = "jamesb7/fuel-prices-uk"

logger = logging.getLogger(__name__)


def main(timer: func.TimerRequest) -> None:
    logger.info("UK Fuel ingest function triggered.")

    conn = None
    rows_stations = 0
    rows_prices = 0

    try:
        conn = get_connection()
        latest_recorded_at = get_latest_recorded_at(conn)
        logger.info("Latest recorded_at in DB: %s", latest_recorded_at)

        with tempfile.TemporaryDirectory() as tmpdir:
            _download_dataset(tmpdir)

            stations_path = os.path.join(tmpdir, "stations.csv")
            prices_path = os.path.join(tmpdir, "price_history.csv")

            rows_stations = _ingest_stations(conn, stations_path)
            logger.info("Stations upserted: %d", rows_stations)

            rows_prices = _ingest_prices(conn, prices_path, latest_recorded_at)
            logger.info("Price history rows inserted: %d", rows_prices)

        log_run(conn, rows_stations, rows_prices, "success")
        logger.info("Ingest complete.")

    except Exception as exc:
        logger.exception("Ingest failed: %s", exc)
        if conn:
            try:
                log_run(conn, rows_stations, rows_prices, "error", str(exc))
            except Exception:
                pass
        raise

    finally:
        if conn:
            conn.close()


def _download_dataset(dest_dir: str) -> None:
    import kaggle  # noqa: PLC0415 — import here so env vars are already set

    logger.info("Downloading Kaggle dataset: %s", KAGGLE_DATASET)
    kaggle.api.authenticate()
    kaggle.api.dataset_download_files(KAGGLE_DATASET, path=dest_dir, unzip=True)
    logger.info("Download complete. Files: %s", os.listdir(dest_dir))


def _ingest_stations(conn, path: str) -> int:
    df = pd.read_csv(path)

    # Drop the mostly-empty organisation_name column if present
    df = df.drop(columns=["organisation_name"], errors="ignore")

    # Fill nulls in text columns
    for col in ["brand_name", "city", "county"]:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")

    # Parse datetime columns
    for col in ["first_seen", "last_seen", "updated_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
            df[col] = df[col].where(df[col].notna(), None)

    rows = df.to_dict(orient="records")
    return upsert_stations(conn, rows)


def _ingest_prices(conn, path: str, latest_recorded_at) -> int:
    df = pd.read_csv(path)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True, errors="coerce")
    df["source_updated_at"] = pd.to_datetime(df["source_updated_at"], utc=True, errors="coerce")

    # Delta load: only rows newer than what's already in the DB
    if latest_recorded_at is not None:
        df = df[df["recorded_at"] > pd.Timestamp(latest_recorded_at, tz="UTC")]
        logger.info("After delta filter: %d rows to insert", len(df))

    if df.empty:
        logger.info("No new price records to insert.")
        return 0

    rows = df[["node_id", "fuel_type", "price_pence", "recorded_at", "source_updated_at"]].to_dict(
        orient="records"
    )
    return insert_price_history_delta(conn, rows)
