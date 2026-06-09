"""XGBoost per-station price prediction. Biweekly: 1st and 15th at 03:00 UTC."""
from __future__ import annotations

import logging, os, sys
from datetime import datetime

import azure.functions as func
import pandas as pd
import xgboost as xgb
from psycopg2.extras import execute_values
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
    logger.info("Loaded %d rows for XGBoost.", len(df))
    encoders = {}
    for col in ["fuel_type", "brand_name", "city", "county"]:
        le = LabelEncoder()
        df[f"{col}_enc"] = le.fit_transform(df[col].fillna("Unknown"))
        encoders[col] = le
    model = xgb.XGBRegressor(
        n_estimators=100, max_depth=6, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8, tree_method="hist",
        n_jobs=-1, random_state=42,
    )
    model.fit(df[FEATURE_COLS], df["price_pence"], verbose=False)
    return {"model": model, "encoders": encoders, "feature_cols": FEATURE_COLS}


def store_predictions(conn, bundle: dict) -> None:
    model    = bundle["model"]
    encoders = bundle["encoders"]

    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (node_id) node_id, latitude, longitude,
                is_motorway, is_supermarket, is_temporarily_closed, is_permanently_closed,
                brand_name, city, county
            FROM fuel_prices ORDER BY node_id, recorded_at DESC
        """)
        stations = cur.fetchall()

    now = datetime.utcnow()

    def enc(e, v):
        return int(e.transform([v])[0]) if v in e.classes_ else 0

    feature_rows, labels = [], []
    for node_id, lat, lon, is_mw, is_sm, is_tc, is_pc, brand, city, county in stations:
        for ft in ["E10", "E5", "B7", "SDV"]:
            feature_rows.append({
                "latitude": lat, "longitude": lon,
                "year": now.year, "month": now.month, "day": now.day,
                "day_of_week": now.weekday(), "hour": 12,
                "is_motorway": is_mw, "is_supermarket": is_sm,
                "is_temporarily_closed": is_tc, "is_permanently_closed": is_pc,
                "fuel_type_enc":  enc(encoders["fuel_type"],  ft),
                "brand_name_enc": enc(encoders["brand_name"], brand),
                "city_enc":       enc(encoders["city"],       city),
                "county_enc":     enc(encoders["county"],     county),
            })
            labels.append((node_id, ft, brand, city, county, lat, lon))

    preds = model.predict(pd.DataFrame(feature_rows)[FEATURE_COLS])

    rows = [
        (labels[i][0], labels[i][1], round(float(preds[i]), 2),
         labels[i][2], labels[i][3], labels[i][4], labels[i][5], labels[i][6])
        for i in range(len(labels))
    ]

    with conn.cursor() as cur:
        cur.execute("DELETE FROM ml_predictions")
        execute_values(cur, """
            INSERT INTO ml_predictions
                (node_id, fuel_type, predicted_pence, brand_name, city, county, latitude, longitude)
            VALUES %s
        """, rows, page_size=1000)
    conn.commit()
    logger.info("Stored %d predictions for %d stations.", len(rows), len(stations))


def main(timer: func.TimerRequest) -> None:
    logger.info("XGBoost training started.")
    conn = None
    try:
        conn = get_connection()
        bundle = train(conn)
        save_model(MODEL_NAME, bundle)
        store_predictions(conn, bundle)
        logger.info("XGBoost complete.")
    except Exception:
        logger.exception("XGBoost failed — previous model unchanged.")
        raise
    finally:
        if conn: conn.close()
