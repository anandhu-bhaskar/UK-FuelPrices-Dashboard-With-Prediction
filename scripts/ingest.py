"""
Standalone ingest script — runs via GitHub Actions every Monday.
Downloads the Kaggle UK fuel dataset and delta-loads it into PostgreSQL.
"""

import logging
import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from azure_function.shared.db import (
    get_connection,
    get_latest_recorded_at,
    insert_price_history_delta,
    log_run,
    upsert_stations,
)

KAGGLE_DATASET = "jamesb7/fuel-prices-uk"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def download_dataset(dest_dir: str) -> None:
    import kaggle

    logger.info("Authenticating with Kaggle...")
    kaggle.api.authenticate()
    logger.info("Downloading %s ...", KAGGLE_DATASET)
    kaggle.api.dataset_download_files(KAGGLE_DATASET, path=dest_dir, unzip=True)
    logger.info("Downloaded files: %s", os.listdir(dest_dir))


def ingest_stations(conn, path: str) -> int:
    df = pd.read_csv(path)
    df = df.drop(columns=["organisation_name"], errors="ignore")

    for col in ["brand_name", "city", "county"]:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")

    for col in ["first_seen", "last_seen", "updated_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
            df[col] = df[col].where(df[col].notna(), None)

    return upsert_stations(conn, df.to_dict(orient="records"))


def ingest_prices(conn, path: str, latest_recorded_at) -> int:
    df = pd.read_csv(path)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True, errors="coerce")
    df["source_updated_at"] = pd.to_datetime(df["source_updated_at"], utc=True, errors="coerce")

    if latest_recorded_at is not None:
        df = df[df["recorded_at"] > pd.Timestamp(latest_recorded_at, tz="UTC")]

    if df.empty:
        logger.info("No new price records — DB is already up to date.")
        return 0

    logger.info("%d new price rows to insert.", len(df))
    cols = ["node_id", "fuel_type", "price_pence", "recorded_at", "source_updated_at"]
    return insert_price_history_delta(conn, df[cols].to_dict(orient="records"))


def main() -> None:
    conn = None
    rows_stations = rows_prices = 0
    try:
        conn = get_connection()
        latest = get_latest_recorded_at(conn)
        logger.info("Latest recorded_at in DB: %s", latest)

        with tempfile.TemporaryDirectory() as tmpdir:
            download_dataset(tmpdir)

            rows_stations = ingest_stations(conn, os.path.join(tmpdir, "stations.csv"))
            logger.info("Stations upserted: %d", rows_stations)

            rows_prices = ingest_prices(conn, os.path.join(tmpdir, "price_history.csv"), latest)
            logger.info("Price rows inserted: %d", rows_prices)

        log_run(conn, rows_stations, rows_prices, "success")
        logger.info("Ingest complete.")

    except Exception as exc:
        logger.exception("Ingest failed.")
        if conn:
            try:
                log_run(conn, rows_stations, rows_prices, "error", str(exc))
            except Exception:
                pass
        sys.exit(1)

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
