"""
SNARIMAX time-series model.
Trains one model per fuel type on daily national mean price.
Biweekly timer: 1st and 15th of each month at 02:00 UTC.
"""

from __future__ import annotations

import logging
import os
import sys

import azure.functions as func
import pandas as pd
from river import time_series

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.db import get_connection
from shared.model_store import save_model

logger = logging.getLogger(__name__)

MODEL_NAME = "snarimax"
SNARIMAX_PARAMS = dict(p=7, d=1, q=0, m=7)


def train(conn) -> dict:
    df = pd.read_sql(
        """
        SELECT fuel_type,
               recorded_at::date AS date,
               AVG(price_pence)  AS mean_price
        FROM fuel_prices
        GROUP BY fuel_type, recorded_at::date
        ORDER BY fuel_type, date
        """,
        conn,
    )

    models = {}
    for fuel_type, group in df.groupby("fuel_type"):
        group = group.sort_values("date")
        model = time_series.SNARIMAX(**SNARIMAX_PARAMS)
        for _, row in group.iterrows():
            model.learn_one(x={}, y=float(row["mean_price"]))
        models[fuel_type] = model
        logger.info("SNARIMAX trained: %s (%d days).", fuel_type, len(group))

    return models


def main(timer: func.TimerRequest) -> None:
    logger.info("SNARIMAX training started.")
    conn = None
    try:
        conn = get_connection()
        models = train(conn)
        save_model(MODEL_NAME, models)
        logger.info("SNARIMAX training complete.")
    except Exception:
        logger.exception("SNARIMAX training failed — previous model unchanged.")
        raise
    finally:
        if conn:
            conn.close()
