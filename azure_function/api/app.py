from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from ..shared.db import get_connection

logger = logging.getLogger(__name__)

app = FastAPI(title="UK Fuel Price API")
app.add_middleware(CORSMiddleware, allow_origins=["https://anandhu-bhaskar.github.io"], allow_methods=["GET"], allow_headers=["*"])


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


# ── Core ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/prices")
def get_prices(fuel_type: Optional[str] = None, county: Optional[str] = None,
               limit: int = Query(default=200, le=2000)):
    filters, params = [], []
    if fuel_type: filters.append("fuel_type = %s"); params.append(fuel_type)
    if county:    filters.append("county = %s");    params.append(county)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return _q(f"""
        SELECT node_id, fuel_type, price_pence, recorded_at,
               latitude, longitude, brand_name, city, county
        FROM fuel_prices {where} ORDER BY recorded_at DESC LIMIT %s
    """, params + [limit])


@app.get("/stations")
def get_stations():
    return _q("""
        SELECT DISTINCT ON (node_id)
            node_id, latitude, longitude, brand_name, city, county, is_motorway, is_supermarket
        FROM fuel_prices ORDER BY node_id, recorded_at DESC
    """)


# ── ML — all read from DB cache (written by training functions) ───────────────

@app.get("/forecast/{fuel_type}")
def get_forecast(fuel_type: str, horizon: int = Query(default=7, le=30)):
    data = _q("""
        SELECT forecast_date AS date, predicted_pence, computed_at
        FROM ml_forecasts
        WHERE fuel_type = %s AND forecast_date >= CURRENT_DATE
        ORDER BY forecast_date LIMIT %s
    """, (fuel_type, horizon))
    if not data:
        raise HTTPException(503, "Forecasts not yet computed — runs on 1st/15th")
    return data


@app.get("/anomalies")
def get_anomalies(fuel_type: Optional[str] = None):
    extra = "AND a.fuel_type = %s" if fuel_type else ""
    params = (fuel_type,) if fuel_type else ()
    return _q(f"""
        SELECT a.node_id, a.fuel_type, a.price_pence,
               a.lower_threshold, a.upper_threshold, a.detected_at,
               fp.latitude, fp.longitude, fp.brand_name, fp.city, fp.county
        FROM ml_anomalies a
        JOIN LATERAL (
            SELECT latitude, longitude, brand_name, city, county
            FROM fuel_prices WHERE node_id = a.node_id LIMIT 1
        ) fp ON true
        WHERE 1=1 {extra}
        ORDER BY a.detected_at DESC
    """, params)


@app.get("/predict")
def predict_price(node_id: str, fuel_type: str):
    row = _q("""
        SELECT node_id, fuel_type, predicted_pence, brand_name, city, county, computed_at
        FROM ml_predictions WHERE node_id = %s AND fuel_type = %s
    """, (node_id, fuel_type), many=False)
    if not row:
        raise HTTPException(503, "Predictions not yet computed — runs on 1st/15th")
    return row


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/stats/status")
def system_status():
    return _q("""
        SELECT
            (SELECT MAX(ran_at)      FROM ingest_log WHERE status = 'success') AS last_ingest,
            (SELECT MAX(recorded_at) FROM fuel_prices)                          AS last_data,
            (SELECT MAX(computed_at) FROM ml_forecasts)                         AS last_forecast,
            (SELECT MAX(detected_at) FROM ml_anomalies)                         AS last_anomaly_check,
            (SELECT MAX(computed_at) FROM ml_predictions)                       AS last_predictions,
            (SELECT COUNT(*)         FROM fuel_prices)                          AS total_readings,
            (SELECT COUNT(DISTINCT node_id) FROM fuel_prices)                   AS total_stations
    """, many=False)


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


# County → region mapping (lowercase keys)
_COUNTY_REGION: dict[str, str] = {
    # Scotland
    "aberdeen city": "scotland", "aberdeenshire": "scotland", "angus": "scotland",
    "argyll and bute": "scotland", "clackmannanshire": "scotland",
    "dumfries and galloway": "scotland", "dundee city": "scotland",
    "east ayrshire": "scotland", "east dunbartonshire": "scotland",
    "east lothian": "scotland", "east renfrewshire": "scotland",
    "city of edinburgh": "scotland", "edinburgh": "scotland",
    "falkirk": "scotland", "fife": "scotland",
    "glasgow city": "scotland", "glasgow": "scotland",
    "highland": "scotland", "inverclyde": "scotland",
    "midlothian": "scotland", "moray": "scotland",
    "na h-eileanan an iar": "scotland", "north ayrshire": "scotland",
    "north lanarkshire": "scotland", "orkney islands": "scotland",
    "perth and kinross": "scotland", "renfrewshire": "scotland",
    "scottish borders": "scotland", "shetland islands": "scotland",
    "south ayrshire": "scotland", "south lanarkshire": "scotland",
    "stirling": "scotland", "west dunbartonshire": "scotland", "west lothian": "scotland",
    # Wales
    "blaenau gwent": "wales", "bridgend": "wales", "caerphilly": "wales",
    "cardiff": "wales", "carmarthenshire": "wales", "ceredigion": "wales",
    "conwy": "wales", "denbighshire": "wales", "flintshire": "wales",
    "gwynedd": "wales", "isle of anglesey": "wales", "merthyr tydfil": "wales",
    "monmouthshire": "wales", "neath port talbot": "wales", "newport": "wales",
    "pembrokeshire": "wales", "powys": "wales", "rhondda cynon taf": "wales",
    "swansea": "wales", "torfaen": "wales", "vale of glamorgan": "wales", "wrexham": "wales",
    # Northern Ireland
    "antrim and newtownabbey": "ni", "ards and north down": "ni",
    "armagh city banbridge and craigavon": "ni", "belfast": "ni",
    "causeway coast and glens": "ni", "derry city and strabane": "ni",
    "fermanagh and omagh": "ni", "lisburn and castlereagh": "ni",
    "mid and east antrim": "ni", "mid ulster": "ni", "newry mourne and down": "ni",
    "county antrim": "ni", "county armagh": "ni", "county down": "ni",
    "county fermanagh": "ni", "county londonderry": "ni", "county tyrone": "ni",
    "antrim": "ni", "armagh": "ni", "down": "ni",
    "fermanagh": "ni", "londonderry": "ni", "tyrone": "ni",
}


@app.get("/stats/national-average")
def national_average(
    period: str = Query(default="today", pattern="^(today|7d|30d|90d)$"),
    region: str = Query(default="all",   pattern="^(all|england|scotland|wales|ni)$"),
):
    # Build current and previous window conditions (period-over-period comparison)
    if period == "today":
        cur_cond  = "DATE(fp.recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)"
        prev_cond = "DATE(fp.recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices) - INTERVAL '7 days'"
        union_cond = f"({cur_cond} OR {prev_cond})"
    else:
        days = {"7d": 7, "30d": 30, "90d": 90}[period]
        cur_cond   = f"fp.recorded_at >= NOW() - INTERVAL '{days} days'"
        prev_cond  = f"fp.recorded_at >= NOW() - INTERVAL '{days * 2} days' AND fp.recorded_at < NOW() - INTERVAL '{days} days'"
        union_cond = f"fp.recorded_at >= NOW() - INTERVAL '{days * 2} days'"

    # Region filter
    if region == "all":
        region_sql = ""
        region_params: list = []
    elif region == "england":
        non_england = list({c for c, r in _COUNTY_REGION.items() if r != "england"})
        region_sql = "AND LOWER(COALESCE(fp.county,'')) != ALL(%s::text[])"
        region_params = [non_england]
    else:
        counties = list({c for c, r in _COUNTY_REGION.items() if r == region})
        region_sql = "AND LOWER(COALESCE(fp.county,'')) = ANY(%s::text[])"
        region_params = [counties]

    # Single-pass query: compute current + previous period averages with conditional aggregation
    sql = f"""
        SELECT fp.fuel_type,
               ROUND(AVG(CASE WHEN {cur_cond}  THEN fp.price_pence END)::numeric, 2) AS avg_price,
               ROUND(MIN(CASE WHEN {cur_cond}  THEN fp.price_pence END)::numeric, 2) AS min_price,
               ROUND(MAX(CASE WHEN {cur_cond}  THEN fp.price_pence END)::numeric, 2) AS max_price,
               COUNT(DISTINCT CASE WHEN {cur_cond} THEN fp.node_id END)              AS station_count,
               COUNT(CASE WHEN {cur_cond} THEN 1 END)                                AS reading_count,
               MAX(CASE WHEN {cur_cond}  THEN fp.recorded_at END)                   AS last_updated,
               ROUND(AVG(CASE WHEN {prev_cond} THEN fp.price_pence END)::numeric, 2) AS prev_avg_price
        FROM fuel_prices fp
        WHERE {union_cond} {region_sql}
        GROUP BY fp.fuel_type
        HAVING AVG(CASE WHEN {cur_cond} THEN fp.price_pence END) IS NOT NULL
        ORDER BY fp.fuel_type
    """
    return _q(sql, tuple(region_params))


@app.get("/stats/price-change")
def price_change():
    return _q("""
        WITH latest_day AS (SELECT DATE(MAX(recorded_at)) AS d FROM fuel_prices)
        SELECT fuel_type,
               ROUND(AVG(CASE WHEN DATE(recorded_at) = ld.d THEN price_pence END)::numeric, 2)                    AS current_avg,
               ROUND(AVG(CASE WHEN DATE(recorded_at) = ld.d - INTERVAL '7 days' THEN price_pence END)::numeric, 2) AS week_ago_avg,
               ROUND(AVG(CASE WHEN DATE(recorded_at) = ld.d - INTERVAL '30 days' THEN price_pence END)::numeric, 2) AS month_ago_avg
        FROM fuel_prices, latest_day ld
        WHERE DATE(recorded_at) IN (ld.d, ld.d - INTERVAL '7 days', ld.d - INTERVAL '30 days')
        GROUP BY fuel_type ORDER BY fuel_type
    """)


@app.get("/stats/price-trend")
def price_trend(days: int = Query(default=30, le=365)):
    return _q("""
        SELECT DATE(recorded_at) AS date, fuel_type,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price
        FROM fuel_prices
        WHERE recorded_at >= (SELECT MAX(recorded_at) FROM fuel_prices) - (%s || ' days')::interval
        GROUP BY DATE(recorded_at), fuel_type ORDER BY date, fuel_type
    """, (days,))


@app.get("/stats/by-county")
def by_county(fuel_type: str = "E10"):
    return _q("""
        SELECT county, ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               COUNT(DISTINCT node_id) AS station_count
        FROM fuel_prices
        WHERE fuel_type = %s AND DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY county ORDER BY avg_price ASC
    """, (fuel_type,))


@app.get("/stats/by-brand")
def by_brand(fuel_type: str = "E10"):
    return _q("""
        SELECT brand_name, ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               COUNT(DISTINCT node_id) AS station_count
        FROM fuel_prices
        WHERE fuel_type = %s AND DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY brand_name ORDER BY avg_price ASC LIMIT 30
    """, (fuel_type,))


@app.get("/stats/by-day-of-week")
def by_dow(fuel_type: str = "E10"):
    return _q("""
        SELECT day_of_week, ROUND(AVG(price_pence)::numeric, 2) AS avg_price
        FROM fuel_prices WHERE fuel_type = %s
        GROUP BY day_of_week ORDER BY day_of_week
    """, (fuel_type,))


@app.get("/stats/by-month")
def by_month(fuel_type: str = "E10"):
    return _q("""
        SELECT month, ROUND(AVG(price_pence)::numeric, 2) AS avg_price
        FROM fuel_prices WHERE fuel_type = %s
        GROUP BY month ORDER BY month
    """, (fuel_type,))


@app.get("/stats/cheapest-stations")
def cheapest_stations(fuel_type: str = "E10", limit: int = Query(default=10, le=50)):
    return _q("""
        SELECT node_id, brand_name, city, county,
               ROUND(AVG(price_pence)::numeric, 2) AS avg_price, latitude, longitude
        FROM fuel_prices
        WHERE fuel_type = %s AND DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY node_id, brand_name, city, county, latitude, longitude
        ORDER BY avg_price ASC LIMIT %s
    """, (fuel_type, limit))


@app.get("/stats/motorway-compare")
def motorway_compare():
    return _q("""
        SELECT is_motorway, fuel_type, ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               COUNT(DISTINCT node_id) AS station_count
        FROM fuel_prices
        WHERE DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY is_motorway, fuel_type ORDER BY fuel_type, is_motorway
    """)


@app.get("/stats/supermarket-compare")
def supermarket_compare():
    return _q("""
        SELECT is_supermarket, fuel_type, ROUND(AVG(price_pence)::numeric, 2) AS avg_price,
               COUNT(DISTINCT node_id) AS station_count
        FROM fuel_prices
        WHERE DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY is_supermarket, fuel_type ORDER BY fuel_type, is_supermarket
    """)


@app.get("/stats/distribution")
def distribution(fuel_type: str = "E10"):
    return _q("""
        SELECT (FLOOR(price_pence / 2) * 2)::int AS bucket, COUNT(*) AS count
        FROM fuel_prices
        WHERE fuel_type = %s AND DATE(recorded_at) = (SELECT DATE(MAX(recorded_at)) FROM fuel_prices)
        GROUP BY bucket ORDER BY bucket
    """, (fuel_type,))


@app.get("/stats/station-count-by-county")
def station_count_by_county():
    return _q("""
        SELECT county, COUNT(DISTINCT node_id) AS station_count
        FROM fuel_prices GROUP BY county ORDER BY station_count DESC LIMIT 25
    """)


@app.get("/stats/predicted-cheapest")
def predicted_cheapest(fuel_type: str = "E10", limit: int = Query(default=10, le=50)):
    data = _q("""
        SELECT node_id, fuel_type, predicted_pence, brand_name, city, county, latitude, longitude
        FROM ml_predictions WHERE fuel_type = %s ORDER BY predicted_pence ASC LIMIT %s
    """, (fuel_type, limit))
    if not data:
        raise HTTPException(503, "Predictions not yet computed — runs on 1st/15th")
    return data
