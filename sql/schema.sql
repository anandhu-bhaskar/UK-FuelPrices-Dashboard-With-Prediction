-- Single flat table: merged, cleaned, feature-engineered at ingest time.
-- ML reads directly from here. Dashboard reads directly from here.

CREATE TABLE IF NOT EXISTS fuel_prices (
    id                    BIGSERIAL PRIMARY KEY,
    node_id               TEXT NOT NULL,
    recorded_at           TIMESTAMPTZ NOT NULL,
    price_pence           NUMERIC(6, 1) NOT NULL,
    fuel_type             TEXT NOT NULL,
    -- Time features (pre-computed at ingest)
    year                  INTEGER NOT NULL,
    month                 INTEGER NOT NULL,
    day                   INTEGER NOT NULL,
    day_of_week           INTEGER NOT NULL,
    hour                  INTEGER NOT NULL,
    -- Station features
    latitude              DOUBLE PRECISION NOT NULL,
    longitude             DOUBLE PRECISION NOT NULL,
    is_motorway           INTEGER NOT NULL DEFAULT 0,
    is_supermarket        INTEGER NOT NULL DEFAULT 0,
    is_temporarily_closed INTEGER NOT NULL DEFAULT 0,
    is_permanently_closed INTEGER NOT NULL DEFAULT 0,
    brand_name            TEXT NOT NULL,
    city                  TEXT NOT NULL,
    county                TEXT NOT NULL,
    CONSTRAINT fuel_prices_unique UNIQUE (node_id, fuel_type, recorded_at)
);

CREATE INDEX IF NOT EXISTS idx_fuel_prices_recorded_at
    ON fuel_prices (recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_fuel_prices_fuel_type
    ON fuel_prices (fuel_type, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_fuel_prices_node
    ON fuel_prices (node_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS ingest_log (
    id                   BIGSERIAL PRIMARY KEY,
    ran_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rows_inserted        INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL,
    kaggle_last_updated  TEXT,
    error_message        TEXT
);
