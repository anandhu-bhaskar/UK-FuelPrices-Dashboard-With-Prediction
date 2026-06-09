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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

_cache: dict = {}


def _model(name):
    if name not in _cache:
        _cache[name] = load_model(name)
    return _cache[name]


def _json(name):
    if name not in _cache:
        _cache[name] = load_json(name)
    return _cache[name]


def _s(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _q(sql: str, params=(), many=True):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        result = [_s(dict(zip(cols, r))) for r in rows]
        return result if many else (result[0] if result else None)
    finally:
        conn.close()


# ── Core ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/prices")
def get_prices(fuel_type: Optional[str] = None, county: Optional[str] = None,
               limit: int = Query(default=200, le=2000)):
    filters, params = [], []
    if fuel_type:
        filters.append("fuel_type = %s"); params.append(fuel_type)
    if county:
        filters.append("county = %s"); params.append(county)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return _q(f"""
        SELECT node_id, fuel_type, price_pence, recorded_at,
               latitude, longitude, brand_name, city, county
        FROM fuel_prices {where}
        ORDER BY recorded_at DESC LIMIT %s
    """, params + [limit])


@app.get("/stations")
def get_stations():
    return _q("""
        SELECT DISTINCT ON (node_id)
            node_id, latitude, longitude, brand_name, city, county,
            is_motorway, is_supermarket
        FROM fuel_prices ORDER BY node_id, recorded_at DESC
    """)


@app.get("/forecast/{fuel_type}")
def get_forecast(fuel_type: str, horizon: int = Query(default=7, le=30)):
    try:
        models = _model("snarimax")
    except Exception:
        raise HTTPException(503, "SNARIMAX model not yet trained")
    if fuel_type not in models:
        raise HTTPException(404, f"No model for {fuel_type}")
    values = models[fuel_type].forecast(horizon=horizon)
    base = datetime.utcnow().date()
    return [{"date": str(base + timedelta(days=i + 1)), "predicted_pence": round(v, 2)}
            for i, v in enumerate(values)]


@app.get("/predict")
def predict_price(node_id: str, fuel_type: str):
    try:
        bundle = _model("xgboost")
    except Exception:
        raise HTTPException(503, "XGBoost model not yet trained")
    model, encoders, feature_cols = bundle["model"], bundle["encoders"], bundle["feature_cols"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT latitude, longitude, is_motorway, is_supermarket,
                       is_temporarily_closed, is_permanently_closed,
                       brand_name, city, county
                FROM fuel_prices WHERE node_id = %s LIMIT 1
            """, (node_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, f"Station {node_id} not found")
    lat, lon, is_mw, is_sm, is_tc, is_pc, brand, city, county = row
    now = datetime.utcnow()
    def enc(e, v): return int(e.transform([v])[0]) if v in e.classes_ else 0
    X = pd.DataFrame([{
        "latitude": lat, "longitude": lon,
        "year": now.year, "month": now.month, "day": now.day,
        "day_of_week": now.weekday(), "hour": now.hour,
        "is_motorway": is_mw, "is_supermarket": is_sm,
        "is_temporarily_closed": is_tc, "is_permanently_closed": is_pc,
        "fuel_type_enc": enc(encoders["fuel_type"], fuel_type),
        "brand_name_enc": enc(encoders["brand_name"], brand),
        "city_enc": enc(encoders["city"], city),
        "county_enc": enc(encoders["county"], county),
    }])[feature_cols]
    return {"node_id": node_id, "fuel_type": fuel_type,
            "predicted_pence": round(float(model.predict(X)[0]), 2)}


@app.get("/anomalies")
def get_anomalies(fuel_type: Optional[str] = None):
    try:
        thresholds = _json("anomaly")
    except Exception:
        raise HTTPException(503, "Anomaly thresholds not yet computed")
    rows = _q("""
        SELECT DISTINCT ON (node_id, fuel_type)
            node_id, fuel_type, price_pence, recorded_at,
            latitude, longitude, brand_name, city, county
        FROM fuel_prices {} ORDER BY node_id, fuel_type, recorded_at DESC
    """.format("WHERE fuel_type = %s" if fuel_type else ""),
              (fuel_type,) if fuel_type else ())
    return [
        {**r, "lower_threshold": thresholds[r["fuel_type"]]["lower_threshold"],
              "upper_threshold": thresholds[r["fuel_type"]]["upper_threshold"]}
        for r in rows if r["fuel_type"] in thresholds
        and (float(r["price_pence"]) < thresholds[r["fuel_type"]]["lower_threshold"]
             or float(r["price_pence"]) > thresholds[r["fuel_type"]]["upper_threshold"])
    ]


# ── Analytics ───────────────────────────────────────────────────────────────

@app.get("/stats/fuel-types")
def fuel_types():
    return _q("SELECT DISTINCT fuel_type FROM fuel_prices ORDER BY fuel_type")


@app.get("/stats/summary")
def summary():
    return _q("""
        SELECT fuel_type,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               ROUND(MIN(price_pence)::numeric, 2) AS min_price,
               ROUND(MAX(price_pence)::numeric, 2) AS max_price,
               COUNT(DISTINCT node_id)             AS station_count,
               COUNT(*)                            AS reading_count,
               MAX(recorded_at)                    AS last_updated
        FROM fuel_prices
        WHERE DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY fuel_type ORDER BY fuel_type
    """)


@app.get("/stats/price-change")
def price_change():
    return _q("""
        WITH latest_day AS (SELECT DATE(MAX(recorded_at)) AS d FROM fuel_prices)
        SELECT fuel_type,
               ROUND(AVG(CASE WHEN DATE(recorded_at) = ld.d
                               THEN price_pence END)::numeric, 2)                     AS current_avg,
               ROUND(AVG(CASE WHEN DATE(recorded_at) = ld.d - INTERVAL '7 days'
                               THEN price_pence END)::numeric, 2)                     AS week_ago_avg,
               ROUND(AVG(CASE WHEN DATE(recorded_at) = ld.d - INTERVAL '30 days'
                               THEN price_pence END)::numeric, 2)                     AS month_ago_avg
        FROM fuel_prices, latest_day ld
        WHERE DATE(recorded_at) IN (ld.d, ld.d - INTERVAL '7 days', ld.d - INTERVAL '30 days')
        GROUP BY fuel_type ORDER BY fuel_type
    """)


@app.get("/stats/price-trend")
def price_trend(days: int = Query(default=30, le=365)):
    return _q("""
        SELECT DATE(recorded_at)                   AS date,
               fuel_type,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price
        FROM fuel_prices
        WHERE recorded_at >= (SELECT MAX(recorded_at) FROM fuel_prices) - (%s || ' days')::interval
        GROUP BY DATE(recorded_at), fuel_type
        ORDER BY date, fuel_type
    """, (days,))


@app.get("/stats/by-county")
def by_county(fuel_type: str = "E10"):
    return _q("""
        SELECT county,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               COUNT(DISTINCT node_id)             AS station_count
        FROM fuel_prices
        WHERE fuel_type = %s
          AND DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY county ORDER BY avg_price ASC
    """, (fuel_type,))


@app.get("/stats/by-brand")
def by_brand(fuel_type: str = "E10"):
    return _q("""
        SELECT brand_name,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               COUNT(DISTINCT node_id)             AS station_count
        FROM fuel_prices
        WHERE fuel_type = %s
          AND DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY brand_name ORDER BY avg_price ASC
        LIMIT 30
    """, (fuel_type,))


@app.get("/stats/by-day-of-week")
def by_dow(fuel_type: str = "E10"):
    return _q("""
        SELECT day_of_week,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price
        FROM fuel_prices WHERE fuel_type = %s
        GROUP BY day_of_week ORDER BY day_of_week
    """, (fuel_type,))


@app.get("/stats/by-month")
def by_month(fuel_type: str = "E10"):
    return _q("""
        SELECT month,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price
        FROM fuel_prices WHERE fuel_type = %s
        GROUP BY month ORDER BY month
    """, (fuel_type,))


@app.get("/stats/cheapest-stations")
def cheapest_stations(fuel_type: str = "E10", limit: int = Query(default=10, le=50)):
    return _q("""
        SELECT node_id, brand_name, city, county,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               latitude, longitude
        FROM fuel_prices
        WHERE fuel_type = %s
          AND DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY node_id, brand_name, city, county, latitude, longitude
        ORDER BY avg_price ASC LIMIT %s
    """, (fuel_type, limit))


@app.get("/stats/motorway-compare")
def motorway_compare():
    return _q("""
        SELECT is_motorway, fuel_type,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               COUNT(DISTINCT node_id)             AS station_count
        FROM fuel_prices
        WHERE DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY is_motorway, fuel_type ORDER BY fuel_type, is_motorway
    """)


@app.get("/stats/supermarket-compare")
def supermarket_compare():
    return _q("""
        SELECT is_supermarket, fuel_type,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               COUNT(DISTINCT node_id)             AS station_count
        FROM fuel_prices
        WHERE DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY is_supermarket, fuel_type ORDER BY fuel_type, is_supermarket
    """)


@app.get("/stats/distribution")
def distribution(fuel_type: str = "E10"):
    return _q("""
        SELECT (FLOOR(price_pence / 2) * 2)::int AS bucket,
               COUNT(*)                          AS count
        FROM fuel_prices
        WHERE fuel_type = %s
          AND DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY bucket ORDER BY bucket
    """, (fuel_type,))


@app.get("/stats/station-count-by-county")
def station_count_by_county():
    return _q("""
        SELECT county, COUNT(DISTINCT node_id) AS station_count
        FROM fuel_prices
        GROUP BY county ORDER BY station_count DESC LIMIT 25
    """)
