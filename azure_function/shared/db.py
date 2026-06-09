import os
import psycopg2
import psycopg2.extras


def get_connection():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSL_MODE", "require"),
    )


def upsert_stations(conn, rows: list[dict]) -> int:
    sql = """
        INSERT INTO stations (
            node_id, trading_name, brand_name, latitude, longitude,
            address_line_1, city, county, postcode,
            is_motorway, is_supermarket, is_temporarily_closed, is_permanently_closed,
            amenities, opening_times, fuel_types,
            first_seen, last_seen, updated_at
        ) VALUES %s
        ON CONFLICT (node_id) DO UPDATE SET
            trading_name          = EXCLUDED.trading_name,
            brand_name            = EXCLUDED.brand_name,
            is_temporarily_closed = EXCLUDED.is_temporarily_closed,
            is_permanently_closed = EXCLUDED.is_permanently_closed,
            last_seen             = EXCLUDED.last_seen,
            updated_at            = EXCLUDED.updated_at
    """
    values = [
        (
            r["node_id"], r["trading_name"], r.get("brand_name"),
            r["latitude"], r["longitude"], r["address_line_1"],
            r.get("city"), r.get("county"), r["postcode"],
            r["is_motorway"], r["is_supermarket"],
            r["is_temporarily_closed"], r["is_permanently_closed"],
            r.get("amenities"), r.get("opening_times"), r.get("fuel_types"),
            r.get("first_seen"), r.get("last_seen"), r.get("updated_at"),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, values, page_size=500)
    conn.commit()
    return len(values)


def insert_price_history_delta(conn, rows: list[dict]) -> int:
    sql = """
        INSERT INTO price_history (node_id, fuel_type, price_pence, recorded_at, source_updated_at)
        VALUES %s
        ON CONFLICT (node_id, fuel_type, recorded_at) DO NOTHING
    """
    values = [
        (r["node_id"], r["fuel_type"], r["price_pence"], r["recorded_at"], r["source_updated_at"])
        for r in rows
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, values, page_size=1000)
    conn.commit()
    return len(values)


def get_latest_recorded_at(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(recorded_at) FROM price_history")
        result = cur.fetchone()
    return result[0] if result and result[0] else None


def log_run(conn, rows_stations: int, rows_prices: int, status: str, error: str | None = None):
    sql = """
        INSERT INTO ingest_log (ran_at, rows_stations, rows_prices, status, error_message)
        VALUES (NOW(), %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (rows_stations, rows_prices, status, error))
    conn.commit()
