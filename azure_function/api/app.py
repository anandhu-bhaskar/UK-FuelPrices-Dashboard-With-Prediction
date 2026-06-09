from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from ..shared.db import get_connection
from ..shared.model_store import load_json, load_model

logger = logging.getLogger(__name__)

app = FastAPI(title="UK Fuel Price API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Module-level model cache — loaded once per worker instance
_cache: dict = {}


def _get_model(name: str):
    if name not in _cache:
        _cache[name] = load_model(name)
    return _cache[name]


def _get_json(name: str):
    if name not in _cache:
        _cache[name] = load_json(name)
    return _cache[name]


def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/prices")
def get_prices(
    fuel_type: Optional[str] = None,
    county: Optional[str] = None,
    limit: int = Query(default=200, le=2000),
):
    conn = get_connection()
    try:
        filters, params = [], []
        if fuel_type:
            filters.append("fuel_type = %s")
            params.append(fuel_type)
        if county:
            filters.append("county = %s")
            params.append(county)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT node_id, fuel_type, price_pence, recorded_at,
                       latitude, longitude, brand_name, city, county
                FROM fuel_prices
                {where}
                ORDER BY recorded_at DESC
                LIMIT %s
                """,
                params + [limit],
            )
            cols = [d[0] for d in cur.description]
            return [_serialize(dict(zip(cols, r))) for r in cur.fetchall()]
    finally:
        conn.close()


@app.get("/stations")
def get_stations():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (node_id)
                    node_id, latitude, longitude, brand_name, city, county,
                    is_motorway, is_supermarket
                FROM fuel_prices
                ORDER BY node_id, recorded_at DESC
            """)
            cols = [d[0] for d in cur.description]
            return [_serialize(dict(zip(cols, r))) for r in cur.fetchall()]
    finally:
        conn.close()


@app.get("/forecast/{fuel_type}")
def get_forecast(fuel_type: str, horizon: int = Query(default=7, le=30)):
    try:
        models = _get_model("snarimax")
    except Exception:
        raise HTTPException(status_code=503, detail="SNARIMAX model not yet trained")
    if fuel_type not in models:
        raise HTTPException(status_code=404, detail=f"No model for fuel_type={fuel_type}")
    try:
        values = models[fuel_type].forecast(horizon=horizon)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    base = datetime.utcnow().date()
    return [
        {"date": str(base + timedelta(days=i + 1)), "predicted_pence": round(v, 2)}
        for i, v in enumerate(values)
    ]


@app.get("/predict")
def predict_price(node_id: str, fuel_type: str):
    try:
        bundle = _get_model("xgboost")
    except Exception:
        raise HTTPException(status_code=503, detail="XGBoost model not yet trained")

    model = bundle["model"]
    encoders = bundle["encoders"]
    feature_cols = bundle["feature_cols"]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT latitude, longitude, is_motorway, is_supermarket,
                       is_temporarily_closed, is_permanently_closed,
                       brand_name, city, county
                FROM fuel_prices
                WHERE node_id = %s
                LIMIT 1
                """,
                (node_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Station {node_id} not found")

    lat, lon, is_mw, is_sm, is_tc, is_pc, brand, city, county = row
    now = datetime.utcnow()

    def encode(enc, val):
        return int(enc.transform([val])[0]) if val in enc.classes_ else 0

    features = {
        "latitude": lat, "longitude": lon,
        "year": now.year, "month": now.month, "day": now.day,
        "day_of_week": now.weekday(), "hour": now.hour,
        "is_motorway": is_mw, "is_supermarket": is_sm,
        "is_temporarily_closed": is_tc, "is_permanently_closed": is_pc,
        "fuel_type_enc": encode(encoders["fuel_type"], fuel_type),
        "brand_name_enc": encode(encoders["brand_name"], brand),
        "city_enc": encode(encoders["city"], city),
        "county_enc": encode(encoders["county"], county),
    }

    X = pd.DataFrame([features])[feature_cols]
    return {
        "node_id": node_id,
        "fuel_type": fuel_type,
        "predicted_pence": round(float(model.predict(X)[0]), 2),
    }


@app.get("/anomalies")
def get_anomalies(fuel_type: Optional[str] = None):
    try:
        thresholds = _get_json("anomaly")
    except Exception:
        raise HTTPException(status_code=503, detail="Anomaly thresholds not yet computed")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT DISTINCT ON (node_id, fuel_type)
                    node_id, fuel_type, price_pence, recorded_at,
                    latitude, longitude, brand_name, city, county
                FROM fuel_prices
                {}
                ORDER BY node_id, fuel_type, recorded_at DESC
            """.format("WHERE fuel_type = %s" if fuel_type else "")
            cur.execute(query, (fuel_type,) if fuel_type else ())
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    anomalies = []
    for r in rows:
        ft = r["fuel_type"]
        if ft not in thresholds:
            continue
        price = float(r["price_pence"])
        lo = thresholds[ft]["lower_threshold"]
        hi = thresholds[ft]["upper_threshold"]
        if price < lo or price > hi:
            anomalies.append({
                **_serialize(r),
                "lower_threshold": lo,
                "upper_threshold": hi,
            })
    return anomalies
