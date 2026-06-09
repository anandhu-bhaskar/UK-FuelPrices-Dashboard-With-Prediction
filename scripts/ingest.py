"""
Standalone ingest script — runs via GitHub Actions every Monday.
Downloads the Kaggle UK fuel dataset and delta-loads it into PostgreSQL.
"""

import logging
import os
import sys
import tempfile
import zipfile

import pandas as pd
import requests

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
    token = os.environ["KAGGLE_API_TOKEN"]
    owner, dataset = KAGGLE_DATASET.split("/")
    url = f"https://www.kaggle.com/api/v1/datasets/download/{owner}/{dataset}"
    logger.info("Downloading %s ...", KAGGLE_DATASET)
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, stream=True, timeout=120)
    resp.raise_for_status()
    zip_path = os.path.join(dest_dir, "dataset.zip")
    with open(zip_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest_dir)
    os.remove(zip_path)
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


def ingest_prices(conn, path: str, latest_recorded_at, valid_node_ids: set) -> int:
    df = pd.read_csv(path)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True, errors="coerce")
    df["source_updated_at"] = pd.to_datetime(df["source_updated_at"], utc=True, errors="coerce")

    # Drop rows with unparseable timestamps
    before = len(df)
    df = df.dropna(subset=["recorded_at"])
    if len(df) < before:
        logger.info("Dropped %d rows with null recorded_at.", before - len(df))

    # Filter price outliers — valid UK fuel prices are 100–220 pence/litre
    before = len(df)
    df = df[df["price_pence"].between(100, 220)]
    if len(df) < before:
        logger.info("Dropped %d price outlier rows (outside 100–220p range).", before - len(df))

    # Drop prices with no matching station (FK safety)
    before = len(df)
    df = df[df["node_id"].isin(valid_node_ids)]
    dropped = before - len(df)
    if dropped:
        logger.info("Dropped %d price rows with no matching station.", dropped)

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
        logger.info("Latest price in DB: %s", latest)

        with tempfile.TemporaryDirectory() as tmpdir:
            download_dataset(tmpdir)

            stations_df = pd.read_csv(os.path.join(tmpdir, "stations.csv"))
            valid_node_ids = set(stations_df["node_id"])
            rows_stations = ingest_stations(conn, os.path.join(tmpdir, "stations.csv"))
            logger.info("Stations upserted: %d", rows_stations)

            rows_prices = ingest_prices(conn, os.path.join(tmpdir, "price_history.csv"), latest, valid_node_ids)
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
