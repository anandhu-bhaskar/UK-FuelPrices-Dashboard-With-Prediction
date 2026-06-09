"""
Z-score anomaly detection.
Computes mean and std per fuel type.
A price is anomalous if it is more than 2 std deviations from the mean.
Biweekly timer: 1st and 15th of each month at 04:00 UTC.
"""

from __future__ import annotations

import logging
import os
import sys

import azure.functions as func
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.db import get_connection
from shared.model_store import save_json

logger = logging.getLogger(__name__)

MODEL_NAME = "anomaly"
Z_THRESHOLD = 2.0


def train(conn) -> dict:
    df = pd.read_sql(
        "SELECT fuel_type, price_pence FROM fuel_prices",
        conn,
    )

    thresholds = {}
    for fuel_type, group in df.groupby("fuel_type"):
        mean  = float(group["price_pence"].mean())
        std   = float(group["price_pence"].std())
        thresholds[fuel_type] = {
            "mean":            mean,
            "std":             std,
            "upper_threshold": mean + Z_THRESHOLD * std,
            "lower_threshold": mean - Z_THRESHOLD * std,
            "z_threshold":     Z_THRESHOLD,
        }
        logger.info(
            "Anomaly thresholds for %s: mean=%.2f std=%.2f (%.2f–%.2fp).",
            fuel_type, mean, std,
            thresholds[fuel_type]["lower_threshold"],
            thresholds[fuel_type]["upper_threshold"],
        )

    return thresholds


def main(timer: func.TimerRequest) -> None:
    logger.info("Anomaly detection training started.")
    conn = None
    try:
        conn = get_connection()
        thresholds = train(conn)
        save_json(MODEL_NAME, thresholds)
        logger.info("Anomaly thresholds saved.")
    except Exception:
        logger.exception("Anomaly training failed — previous thresholds unchanged.")
        raise
    finally:
        if conn:
            conn.close()
