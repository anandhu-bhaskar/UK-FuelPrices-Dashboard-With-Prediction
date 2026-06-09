"""
XGBoost per-station price prediction.
Features: lat, lon, time features, station flags, fuel type & brand (label encoded).
Biweekly timer: 1st and 15th of each month at 03:00 UTC.
"""

from __future__ import annotations

import logging
import os
import sys

import azure.functions as func
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import LabelEncoder

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.db import get_connection
from shared.model_store import save_model

logger = logging.getLogger(__name__)

MODEL_NAME = "xgboost"
FEATURE_COLS = [
    "latitude", "longitude",
    "year", "month", "day", "day_of_week", "hour",
    "is_motorway", "is_supermarket", "is_temporarily_closed", "is_permanently_closed",
    "fuel_type_enc", "brand_name_enc", "city_enc", "county_enc",
]


def train(conn) -> dict:
    df = pd.read_sql("SELECT * FROM fuel_prices", conn)
    logger.info("Loaded %d rows for XGBoost training.", len(df))

    encoders = {}
    for col in ["fuel_type", "brand_name", "city", "county"]:
        le = LabelEncoder()
        df[f"{col}_enc"] = le.fit_transform(df[col].fillna("Unknown"))
        encoders[col] = le

    X = df[FEATURE_COLS]
    y = df["price_pence"]

    model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        tree_method="hist",
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X, y, verbose=False)
    logger.info("XGBoost trained. Feature importances computed.")

    return {"model": model, "encoders": encoders, "feature_cols": FEATURE_COLS}


def main(timer: func.TimerRequest) -> None:
    logger.info("XGBoost training started.")
    conn = None
    try:
        conn = get_connection()
        result = train(conn)
        save_model(MODEL_NAME, result)
        logger.info("XGBoost training complete.")
    except Exception:
        logger.exception("XGBoost training failed — previous model unchanged.")
        raise
    finally:
        if conn:
            conn.close()
