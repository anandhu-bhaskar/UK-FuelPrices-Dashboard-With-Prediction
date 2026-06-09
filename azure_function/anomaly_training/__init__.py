"""Z-score anomaly detection. Biweekly: 1st and 15th at 04:00 UTC."""
from __future__ import annotations

import logging, os, sys

import azure.functions as func
import pandas as pd
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.db import get_connection
from shared.model_store import save_json

logger = logging.getLogger(__name__)
MODEL_NAME = "anomaly"
Z_THRESHOLD = 2.0


def train(conn) -> dict:
    df = pd.read_sql("SELECT fuel_type, price_pence FROM fuel_prices", conn)
    thresholds = {}
    for fuel_type, group in df.groupby("fuel_type"):
        mean = float(group["price_pence"].mean())
        std  = float(group["price_pence"].std())
        thresholds[fuel_type] = {
            "mean": mean, "std": std,
            "upper_threshold": mean + Z_THRESHOLD * std,
            "lower_threshold": mean - Z_THRESHOLD * std,
            "z_threshold": Z_THRESHOLD,
        }
        logger.info("Anomaly %s: %.2f–%.2fp", fuel_type,
                    thresholds[fuel_type]["lower_threshold"],
                    thresholds[fuel_type]["upper_threshold"])
    return thresholds


def store_anomalies(conn, thresholds: dict) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (node_id, fuel_type)
                node_id, fuel_type, price_pence
            FROM fuel_prices
            WHERE DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
            ORDER BY node_id, fuel_type, recorded_at DESC
        """)
        rows = cur.fetchall()

    anomalies = []
    for node_id, fuel_type, price in rows:
        if fuel_type not in thresholds:
            continue
        lo = thresholds[fuel_type]["lower_threshold"]
        hi = thresholds[fuel_type]["upper_threshold"]
        if float(price) < lo or float(price) > hi:
            anomalies.append((node_id, fuel_type, float(price), lo, hi))

    with conn.cursor() as cur:
        cur.execute("DELETE FROM ml_anomalies")
        if anomalies:
            execute_values(cur, """
                INSERT INTO ml_anomalies (node_id, fuel_type, price_pence, lower_threshold, upper_threshold)
                VALUES %s
            """, anomalies)
    conn.commit()
    logger.info("Stored %d anomalies in DB.", len(anomalies))


def main(timer: func.TimerRequest) -> None:
    logger.info("Anomaly training started.")
    conn = None
    try:
        conn = get_connection()
        thresholds = train(conn)
        save_json(MODEL_NAME, thresholds)
        store_anomalies(conn, thresholds)
        logger.info("Anomaly training complete.")
    except Exception:
        logger.exception("Anomaly training failed — previous thresholds unchanged.")
        raise
    finally:
        if conn: conn.close()
