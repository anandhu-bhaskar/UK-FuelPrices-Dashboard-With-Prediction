"""
Preprocessing pipeline — runs after ingest.py.
Reads raw data from price_history + stations, applies ML transformations,
and saves ml_features.parquet to the data/ directory.
"""

from __future__ import annotations

import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from azure_function.shared.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ml_features.parquet")


def build_ml_features(conn) -> pd.DataFrame:
    logger.info("Loading price_history and stations from DB...")
    df_prices = pd.read_sql(
        "SELECT node_id, fuel_type, price_pence, recorded_at FROM price_history",
        conn,
    )
    df_stations = pd.read_sql(
        """SELECT node_id, latitude, longitude,
                  is_motorway, is_supermarket, is_temporarily_closed, is_permanently_closed,
                  brand_name, city, county
           FROM stations""",
        conn,
    )
    logger.info("Loaded %d price rows, %d stations.", len(df_prices), len(df_stations))

    # Merge
    df = df_prices.merge(df_stations, on="node_id", how="inner")
    logger.info("After merge: %d rows.", len(df))

    # Time features
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
    df["year"]        = df["recorded_at"].dt.year
    df["month"]       = df["recorded_at"].dt.month
    df["day"]         = df["recorded_at"].dt.day
    df["day_of_week"] = df["recorded_at"].dt.dayofweek
    df["hour"]        = df["recorded_at"].dt.hour

    # Boolean → int
    for col in ["is_motorway", "is_supermarket", "is_temporarily_closed", "is_permanently_closed"]:
        df[col] = df[col].fillna(False).astype(int)

    # Fill nulls in categoricals
    for col in ["brand_name", "city", "county"]:
        df[col] = df[col].fillna("Unknown")

    # Label encode (consistent within this run — encodings saved alongside parquet)
    for col in ["brand_name", "city", "county"]:
        df[f"{col}_encoded"] = df[col].astype("category").cat.codes

    # One-hot encode fuel_type
    df = pd.get_dummies(df, columns=["fuel_type"], prefix="fuel")

    # Drop original categorical text columns (not needed for ML)
    df = df.drop(columns=["brand_name", "city", "county"], errors="ignore")

    logger.info("Feature engineering complete. Shape: %s", df.shape)
    return df


def main() -> None:
    conn = None
    try:
        conn = get_connection()
        df = build_ml_features(conn)

        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        df.to_parquet(OUTPUT_PATH, index=False, compression="snappy")
        size_mb = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
        logger.info("Saved ml_features.parquet — %.1f MB, %d rows.", size_mb, len(df))
    except Exception:
        logger.exception("Preprocessing failed.")
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
