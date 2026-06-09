-- Run this once against your Azure PostgreSQL instance to set up the schema.

CREATE TABLE IF NOT EXISTS stations (
    node_id               TEXT PRIMARY KEY,
    trading_name          TEXT NOT NULL,
    brand_name            TEXT,
    latitude              DOUBLE PRECISION NOT NULL,
    longitude             DOUBLE PRECISION NOT NULL,
    address_line_1        TEXT,
    city                  TEXT,
    county                TEXT,
    postcode              TEXT,
    is_motorway           BOOLEAN NOT NULL DEFAULT FALSE,
    is_supermarket        BOOLEAN NOT NULL DEFAULT FALSE,
    is_temporarily_closed BOOLEAN NOT NULL DEFAULT FALSE,
    is_permanently_closed BOOLEAN NOT NULL DEFAULT FALSE,
    amenities             TEXT,
    opening_times         TEXT,
    fuel_types            TEXT,
    first_seen            TIMESTAMPTZ,
    last_seen             TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS price_history (
    id                BIGSERIAL PRIMARY KEY,
    node_id           TEXT NOT NULL REFERENCES stations(node_id) ON DELETE CASCADE,
    fuel_type         TEXT NOT NULL,
    price_pence       NUMERIC(6, 1) NOT NULL,
    recorded_at       TIMESTAMPTZ NOT NULL,
    source_updated_at TIMESTAMPTZ,
    CONSTRAINT price_history_unique UNIQUE (node_id, fuel_type, recorded_at)
);

-- Index for time-series queries (fetch by date range)
CREATE INDEX IF NOT EXISTS idx_price_history_recorded_at
    ON price_history (recorded_at DESC);

-- Index for per-station queries
CREATE INDEX IF NOT EXISTS idx_price_history_node_fuel
    ON price_history (node_id, fuel_type, recorded_at DESC);

-- Index for fuel-type aggregations (national daily average)
CREATE INDEX IF NOT EXISTS idx_price_history_fuel_type
    ON price_history (fuel_type, recorded_at DESC);

CREATE TABLE IF NOT EXISTS ingest_log (
    id            BIGSERIAL PRIMARY KEY,
    ran_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rows_stations INTEGER NOT NULL DEFAULT 0,
    rows_prices   INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL,
    error_message TEXT
);
