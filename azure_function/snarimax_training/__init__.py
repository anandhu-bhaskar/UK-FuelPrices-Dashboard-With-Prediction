"""SNARIMAX time-series model. Biweekly: 1st and 15th at 02:00 UTC."""
from __future__ import annotations

import logging, math, os, sys
from datetime import datetime, timedelta

import azure.functions as func
import pandas as pd
from psycopg2.extras import execute_values
from river import time_series

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.db import get_connection
from shared.model_store import save_model

logger = logging.getLogger(__name__)
MODEL_NAME = "snarimax"
SNARIMAX_PARAMS = dict(p=7, d=1, q=0, m=7)


def train(conn) -> dict:
    df = pd.read_sql("""
        SELECT fuel_type, recorded_at::date AS date, AVG(price_pence) AS mean_price
        FROM fuel_prices GROUP BY fuel_type, recorded_at::date ORDER BY fuel_type, date
    """, conn)
    models = {}
    for fuel_type, group in df.groupby("fuel_type"):
        model = time_series.SNARIMAX(**SNARIMAX_PARAMS)
        for _, row in group.sort_values("date").iterrows():
            model.learn_one(x={}, y=float(row["mean_price"]))
        models[fuel_type] = model
        logger.info("SNARIMAX trained: %s (%d days).", fuel_type, len(group))
    return models


def store_forecasts(conn, models: dict) -> None:
    base = datetime.utcnow().date()
    rows = []
    for fuel_type, model in models.items():
        try:
            values = model.forecast(horizon=7)
            for i, v in enumerate(values):
                if math.isfinite(float(v)):
                    rows.append((fuel_type, base + timedelta(days=i + 1), round(float(v), 2)))
        except Exception as e:
            logger.warning("Forecast failed for %s: %s", fuel_type, e)
    if not rows:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ml_forecasts")
        execute_values(cur, "INSERT INTO ml_forecasts (fuel_type, forecast_date, predicted_pence) VALUES %s", rows)
    conn.commit()
    logger.info("Stored %d forecast rows in DB.", len(rows))


def main(timer: func.TimerRequest) -> None:
    logger.info("SNARIMAX training started.")
    conn = None
    try:
        conn = get_connection()
        models = train(conn)
        save_model(MODEL_NAME, models)
        store_forecasts(conn, models)
        logger.info("SNARIMAX complete.")
    except Exception:
        logger.exception("SNARIMAX failed — previous model unchanged.")
        raise
    finally:
        if conn: conn.close()
