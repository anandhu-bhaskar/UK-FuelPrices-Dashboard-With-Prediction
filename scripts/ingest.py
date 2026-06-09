"""
Weekly ingest: pull from Kaggle, feature-engineer, store in Neon.
Checks dataset last_updated before downloading to skip unnecessary 200MB pulls.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
import tempfile
import zipfile

import kaggle
import pandas as pd
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from azure_function.shared.db import get_connection

KAGGLE_DATASET = "jamesb7/fuel-prices-uk"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Kaggle auth ───────────────────────────────────────────────────────────────

def setup_kaggle_credentials() -> None:
    kaggle_dir = os.path.expanduser("~/.kaggle")
    os.makedirs(kaggle_dir, exist_ok=True)
    creds_path = os.path.join(kaggle_dir, "kaggle.json")
    creds = {
        "username": os.environ["KAGGLE_USERNAME"],
        "key":      os.environ["KAGGLE_KEY"],
    }
    with open(creds_path, "w") as f:
        json.dump(creds, f)
    os.chmod(creds_path, stat.S_IRUSR | stat.S_IWUSR)
    kaggle.api.authenticate()


# ── Freshness check ───────────────────────────────────────────────────────────

def get_kaggle_last_updated() -> str:
    owner, dataset_slug = KAGGLE_DATASET.split("/")
    results = kaggle.api.dataset_list(search=dataset_slug, user=owner)
    for d in results:
        if d.ref == KAGGLE_DATASET:
            return str(d.last_updated)
    return ""


def get_stored_last_updated(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT kaggle_last_updated FROM ingest_log WHERE kaggle_last_updated IS NOT NULL ORDER BY ran_at DESC LIMIT 1"
        )
        row = cur.fetchone()
    return str(row[0]) if row and row[0] else ""


# ── Download ──────────────────────────────────────────────────────────────────

def download_dataset(dest_dir: str) -> None:
    owner, dataset_slug = KAGGLE_DATASET.split("/")
    logger.info("Downloading %s ...", KAGGLE_DATASET)
    kaggle.api.dataset_download_files(KAGGLE_DATASET, path=dest_dir, unzip=True)
    logger.info("Files: %s", os.listdir(dest_dir))


# ── Transform ─────────────────────────────────────────────────────────────────

def build_features(stations_path: str, prices_path: str) -> pd.DataFrame:
    df_stations = pd.read_csv(stations_path)
    df_prices   = pd.read_csv(prices_path)

    # Clean stations
    df_stations = df_stations.drop(columns=["organisation_name"], errors="ignore")
    for col in ["brand_name", "city", "county"]:
        df_stations[col] = df_stations[col].fillna("Unknown")
    for col in ["is_motorway", "is_supermarket", "is_temporarily_closed", "is_permanently_closed"]:
        df_stations[col] = df_stations[col].fillna(False).astype(int)

    # Clean prices
    df_prices["recorded_at"] = pd.to_datetime(df_prices["recorded_at"], utc=True, errors="coerce")
    df_prices = df_prices.dropna(subset=["recorded_at"])
    df_prices = df_prices[df_prices["price_pence"].between(100, 220)]

    # Merge
    df = df_prices.merge(
        df_stations[[
            "node_id", "latitude", "longitude",
            "is_motorway", "is_supermarket", "is_temporarily_closed", "is_permanently_closed",
            "brand_name", "city", "county",
        ]],
        on="node_id",
        how="inner",
    )

    # Time features
    df["year"]        = df["recorded_at"].dt.year
    df["month"]       = df["recorded_at"].dt.month
    df["day"]         = df["recorded_at"].dt.day
    df["day_of_week"] = df["recorded_at"].dt.dayofweek
    df["hour"]        = df["recorded_at"].dt.hour

    logger.info("After merge + clean: %d rows.", len(df))
    return df


# ── Load ──────────────────────────────────────────────────────────────────────

def get_latest_recorded_at(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(recorded_at) FROM fuel_prices")
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def insert_fuel_prices(conn, df: pd.DataFrame) -> int:
    cols = [
        "node_id", "recorded_at", "price_pence", "fuel_type",
        "year", "month", "day", "day_of_week", "hour",
        "latitude", "longitude",
        "is_motorway", "is_supermarket", "is_temporarily_closed", "is_permanently_closed",
        "brand_name", "city", "county",
    ]
    rows = [tuple(r) for r in df[cols].itertuples(index=False)]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO fuel_prices (
                node_id, recorded_at, price_pence, fuel_type,
                year, month, day, day_of_week, hour,
                latitude, longitude,
                is_motorway, is_supermarket, is_temporarily_closed, is_permanently_closed,
                brand_name, city, county
            ) VALUES %s
            ON CONFLICT (node_id, fuel_type, recorded_at) DO NOTHING
            """,
            rows,
            page_size=1000,
        )
    conn.commit()
    return len(rows)


def log_run(conn, rows_inserted: int, status: str, kaggle_last_updated: str = "", error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_log (rows_inserted, status, kaggle_last_updated, error_message) VALUES (%s, %s, %s, %s)",
            (rows_inserted, status, kaggle_last_updated or None, error),
        )
    conn.commit()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    conn = None
    rows_inserted = 0
    kaggle_last_updated = ""
    try:
        setup_kaggle_credentials()
        conn = get_connection()

        # Check if dataset was updated since last successful run
        kaggle_last_updated = get_kaggle_last_updated()
        stored_last_updated = get_stored_last_updated(conn)
        logger.info("Kaggle last updated : %s", kaggle_last_updated)
        logger.info("Our last successful : %s", stored_last_updated)

        if kaggle_last_updated and stored_last_updated and kaggle_last_updated == stored_last_updated:
            logger.info("Dataset unchanged — skipping download.")
            log_run(conn, 0, "skipped", kaggle_last_updated)
            return

        # Download, transform, load
        latest = get_latest_recorded_at(conn)
        with tempfile.TemporaryDirectory() as tmpdir:
            download_dataset(tmpdir)
            df = build_features(
                os.path.join(tmpdir, "stations.csv"),
                os.path.join(tmpdir, "price_history.csv"),
            )

        if latest is not None:
            cutoff = pd.Timestamp(latest).tz_localize("UTC") if latest.tzinfo is None else pd.Timestamp(latest)
            df = df[df["recorded_at"] > cutoff]

        if df.empty:
            logger.info("No new rows after delta filter.")
            log_run(conn, 0, "skipped", kaggle_last_updated)
            return

        logger.info("%d new rows to insert.", len(df))
        rows_inserted = insert_fuel_prices(conn, df)
        log_run(conn, rows_inserted, "success", kaggle_last_updated)
        logger.info("Done. Inserted %d rows.", rows_inserted)

    except Exception as exc:
        logger.exception("Ingest failed.")
        if conn:
            try:
                log_run(conn, rows_inserted, "error", kaggle_last_updated, str(exc))
            except Exception:
                pass
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
