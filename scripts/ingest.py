"""
Weekly ingest: pull from Kaggle, feature-engineer, store in Neon.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import zipfile

import pandas as pd
import requests
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from azure_function.shared.db import get_connection

KAGGLE_DATASET = "jamesb7/fuel-prices-uk"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Download ──────────────────────────────────────────────────────────────────

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
    logger.info("Files: %s", os.listdir(dest_dir))


# ── Transform ─────────────────────────────────────────────────────────────────

def build_features(stations_path: str, prices_path: str) -> pd.DataFrame:
    # Load
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
    logger.info("After merge + clean: %d rows.", len(df))

    # Time features
    df["year"]        = df["recorded_at"].dt.year
    df["month"]       = df["recorded_at"].dt.month
    df["day"]         = df["recorded_at"].dt.day
    df["day_of_week"] = df["recorded_at"].dt.dayofweek
    df["hour"]        = df["recorded_at"].dt.hour

    return df


# ── Load ──────────────────────────────────────────────────────────────────────

def get_latest_recorded_at(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(recorded_at) FROM fuel_prices")
        result = cur.fetchone()
    return result[0] if result and result[0] else None


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


def log_run(conn, rows_inserted: int, status: str, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_log (rows_inserted, status, error_message) VALUES (%s, %s, %s)",
            (rows_inserted, status, error),
        )
    conn.commit()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    conn = None
    rows_inserted = 0
    try:
        conn = get_connection()
        latest = get_latest_recorded_at(conn)
        logger.info("Latest recorded_at in DB: %s", latest)

        with tempfile.TemporaryDirectory() as tmpdir:
            download_dataset(tmpdir)
            df = build_features(
                os.path.join(tmpdir, "stations.csv"),
                os.path.join(tmpdir, "price_history.csv"),
            )

        # Delta: only new rows
        if latest is not None:
            df = df[df["recorded_at"] > pd.Timestamp(latest, tz="UTC")]

        if df.empty:
            logger.info("No new rows — dataset not updated since last run.")
            log_run(conn, 0, "skipped")
            return

        logger.info("%d new rows to insert.", len(df))
        rows_inserted = insert_fuel_prices(conn, df)
        log_run(conn, rows_inserted, "success")
        logger.info("Done. Inserted %d rows.", rows_inserted)

    except Exception as exc:
        logger.exception("Ingest failed.")
        if conn:
            try:
                log_run(conn, rows_inserted, "error", str(exc))
            except Exception:
                pass
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
