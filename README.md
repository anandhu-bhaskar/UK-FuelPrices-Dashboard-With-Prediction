# UK Fuel Price Dashboard & ML Prediction Engine

**Live Application:** [https://anandhu-bhaskar.github.io/UK-FuelPrices-Dashboard-With-Prediction/](https://anandhu-bhaskar.github.io/UK-FuelPrices-Dashboard-With-Prediction/)

**API Base URL:** [https://ukfuel-ml.azurewebsites.net](https://ukfuel-ml.azurewebsites.net)

---

A full-stack, cloud-deployed data engineering and machine learning project built around real-world UK fuel pricing data. The system ingests weekly price readings from thousands of UK filling stations, stores them in a cloud PostgreSQL database, trains three machine learning models on a biweekly schedule, and serves everything through a serverless REST API to an interactive browser dashboard.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Source](#data-source)
3. [Tech Stack](#tech-stack)
4. [Component Breakdown](#component-breakdown)
5. [Machine Learning Models](#machine-learning-models)
6. [Database Schema](#database-schema)
7. [REST API Reference](#rest-api-reference)
8. [Dashboard Features](#dashboard-features)
9. [Deployment](#deployment)
10. [Local Development](#local-development)
11. [Project Structure](#project-structure)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Data Pipeline                               │
│                                                                      │
│   Kaggle API ──► ingest.py (Python/pandas) ──► Neon PostgreSQL      │
│                  (weekly, delta load)              (cloud Postgres)  │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Azure Functions (Serverless)                       │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐              │
│  │  SNARIMAX   │  │   XGBoost    │  │  Z-score      │              │
│  │  Forecast   │  │  Regression  │  │  Anomaly Det. │              │
│  │  (Timer)    │  │  (Timer)     │  │  (Timer)      │              │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘              │
│         │                │                   │                      │
│         └────────────────┼───────────────────┘                      │
│                          ▼                                           │
│              Azure Blob Storage (model versioning)                  │
│                          │                                           │
│              ┌───────────▼──────────┐                               │
│              │    FastAPI REST API   │ ◄── HTTP GET requests        │
│              │    (HTTP Trigger)     │                               │
│              └──────────────────────┘                               │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    GitHub Pages (Frontend)                           │
│                                                                      │
│   Vanilla JS (ES Modules) + Chart.js 4.4 + Leaflet.js 1.9          │
│   Interactive dashboard with 20+ chart types and geospatial map     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Data Source

**Dataset:** [`jamesb7/fuel-prices-uk`](https://www.kaggle.com/datasets/jamesb7/fuel-prices-uk) on Kaggle

The dataset contains historical fuel price readings from UK filling stations, updated regularly. It includes:

| File | Description |
|------|-------------|
| `stations.csv` | Station metadata — brand, city, county, lat/lon, motorway/supermarket flags |
| `price_history.csv` | Daily price readings per station and fuel type |

**Fuel Types Covered:**

| Code | Full Name |
|------|-----------|
| E10 | Standard petrol (unleaded, 10% ethanol) |
| E5 | Premium petrol (super unleaded) |
| B7 / B7_STANDARD | Standard diesel |
| B7_PREMIUM | Premium diesel |
| SDV / HVO | Super diesel / Hydrogenated vegetable oil |
| B10 | High-biodiesel blend |

**Data Volume:** Millions of price readings across 6,000+ UK filling stations. Prices are validated between 100p–220p per litre during ingestion.

---

## Tech Stack

### Backend & Data Engineering

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.11 | Primary backend language |
| FastAPI | 0.115.0 | REST API framework (async, auto-docs) |
| Azure Functions | 1.21.3 | Serverless compute host |
| pandas | 2.2.2 | Data manipulation, ETL pipeline |
| psycopg2 | 2.9.9 | PostgreSQL driver |
| XGBoost | 2.0.3 | Gradient-boosted tree regression |
| scikit-learn | 1.4.2 | Label encoding, preprocessing |
| river | 0.21.2 | Online/incremental ML — SNARIMAX time series |
| azure-storage-blob | 12.20.0 | Model artefact versioning |
| Kaggle API | — | Automated dataset download |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| Vanilla JavaScript (ES Modules) | ES2022 | Dashboard logic, API client |
| Chart.js | 4.4.0 | 15+ chart types (line, bar, doughnut, histogram) |
| Leaflet.js | 1.9.4 | Interactive geospatial station map |
| CSS3 | — | Glassmorphism UI, animations, responsive layout |
| HTML5 | — | Semantic structure |

### Infrastructure

| Service | Provider | Purpose |
|---------|----------|---------|
| Serverless Postgres | Neon | Primary database |
| Serverless Functions | Azure Functions (Consumption) | API + ML training |
| Blob Storage | Azure Storage | Trained model artefacts |
| Static Hosting | GitHub Pages | Frontend delivery |
| Dataset Source | Kaggle | Weekly price data |

---

## Component Breakdown

### 1. Data Ingestion Pipeline (`scripts/ingest.py`)

A Python ETL script that runs weekly to keep the database current:

- **Freshness check** — queries Kaggle's dataset metadata before downloading to skip unnecessary 200 MB pulls when data hasn't changed
- **Download** — uses the official Kaggle Python client to fetch and unzip the dataset to a temporary directory
- **Feature engineering** — joins station metadata to price records, extracts temporal features (`year`, `month`, `day`, `day_of_week`, `hour`), validates price ranges, fills null geographies
- **Delta load** — filters to only new records since the last successful ingest using `MAX(recorded_at)` from the DB
- **Bulk insert** — uses `psycopg2.extras.execute_values` for high-throughput batch insertion with `ON CONFLICT DO NOTHING` deduplication
- **Audit log** — writes every run result (rows inserted, status, kaggle dataset timestamp, errors) to `ingest_log`

### 2. REST API (`azure_function/api/app.py`)

A FastAPI application deployed as an Azure Functions HTTP trigger. All endpoints are read-only (`GET`). CORS is open (`allow_origins=["*"]`). The API serves 20+ endpoints covering:

- Raw price and station data
- Aggregated statistics (by county, brand, day of week, month, distribution)
- ML model outputs (forecasts, anomalies, predictions)
- Comparative analyses (motorway vs regular, supermarket vs regular)
- Filtered national averages (time period × UK region)

See [REST API Reference](#rest-api-reference) for full endpoint list.

### 3. ML Training Functions

Three Azure Functions Timer Triggers run biweekly (1st and 15th of each month):

#### SNARIMAX Forecaster (`azure_function/snarimax_training/`)
Trains at **02:00 UTC** on the 1st and 15th.

#### XGBoost Regression (`azure_function/xgboost_training/`)
Trains at **03:00 UTC** on the 1st and 15th.

#### Z-score Anomaly Detector (`azure_function/anomaly_training/`)
Trains at **04:00 UTC** on the 1st and 15th.

### 4. Model Store (`azure_function/shared/model_store.py`)

Models are persisted to **Azure Blob Storage** with a `latest`/`backup` versioning pattern:

- Before overwriting, the current `{model}/latest.pkl` is promoted to `{model}/backup.pkl`
- If the new upload fails, the previous model survives intact — the dashboard keeps serving predictions
- Pickle is used for XGBoost and SNARIMAX models; JSON for anomaly thresholds

### 5. Frontend Dashboard (`frontend/`)

A zero-framework, vanilla JavaScript single-page application built with ES modules. The API client (`js/api.js`) caches all responses in `localStorage` (30-minute TTL, 24-hour fallback) so the dashboard remains usable when the Azure Function cold-starts.

---

## Machine Learning Models

### SNARIMAX — 7-Day Price Forecasting

**Library:** `river` (online/incremental ML)
**Algorithm:** Seasonal Non-linear AutoRegressive Integrated Moving Average with eXogenous inputs (SNARIMAX)
**Parameters:** `p=7, d=1, q=0, m=7` (weekly seasonality)

- Trained separately for each fuel type on daily national average prices
- Incremental learning: the model is updated one observation at a time, suitable for streaming data
- Produces a 7-day rolling forecast stored in `ml_forecasts`
- Displayed as a line chart in the ML Insights section

**Why SNARIMAX:** The daily price series shows clear weekly periodicity (prices tend to be cheaper mid-week than weekends). The seasonal component `m=7` captures this. The differencing term `d=1` handles the non-stationarity of the price series over time.

### XGBoost — Per-Station Price Regression

**Library:** `xgboost`
**Algorithm:** Gradient Boosted Decision Trees (regression)
**Parameters:** `n_estimators=100, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8, tree_method=hist`

**Features (14 total):**
- Geospatial: `latitude`, `longitude`
- Temporal: `year`, `month`, `day`, `day_of_week`, `hour`
- Station flags: `is_motorway`, `is_supermarket`, `is_temporarily_closed`, `is_permanently_closed`
- Categorical (label-encoded): `fuel_type`, `brand_name`, `city`, `county`

The trained model is applied to every known station × fuel type combination to produce predicted prices, stored in `ml_predictions`. The top 10 cheapest predicted stations per fuel type are surfaced in the dashboard's XGBoost Predictions panel.

**Why XGBoost:** Handles mixed numeric/categorical features well without normalisation. The `hist` tree method is efficient for large datasets. Gradient boosting captures non-linear interactions between location, brand, and temporal patterns that linear models miss.

### Z-score Anomaly Detection

**Algorithm:** Statistical Z-score thresholding
**Threshold:** ±2.0 standard deviations from the per-fuel-type mean

For each fuel type, the training step computes the population mean `μ` and standard deviation `σ` across all historical price readings. Any station reporting today's price outside `[μ - 2σ, μ + 2σ]` is flagged as an anomaly. Anomalies are stored in `ml_anomalies` and displayed as alert cards in the dashboard.

This is equivalent to flagging the most extreme ~5% of prices — catching genuine pricing errors, new station calibration issues, or regional supply disruptions.

---

## Database Schema

**Database:** Neon PostgreSQL (serverless)

### `fuel_prices` — Main fact table

| Column | Type | Description |
|--------|------|-------------|
| `node_id` | TEXT | Station identifier |
| `recorded_at` | TIMESTAMPTZ | Price timestamp (UTC) |
| `price_pence` | NUMERIC | Price in pence per litre |
| `fuel_type` | TEXT | E10, E5, B7_STANDARD, B7_PREMIUM, HVO, B10 |
| `year` | INT | Extracted year |
| `month` | INT | Extracted month (1–12) |
| `day` | INT | Extracted day of month |
| `day_of_week` | INT | 0=Monday … 6=Sunday |
| `hour` | INT | Hour of recording |
| `latitude` | NUMERIC | Station latitude |
| `longitude` | NUMERIC | Station longitude |
| `is_motorway` | INT | 1 if motorway service station |
| `is_supermarket` | INT | 1 if supermarket forecourt |
| `is_temporarily_closed` | INT | Station status |
| `is_permanently_closed` | INT | Station status |
| `brand_name` | TEXT | e.g. BP, Shell, Tesco |
| `city` | TEXT | City/town |
| `county` | TEXT | UK county |

**Primary key / unique constraint:** `(node_id, fuel_type, recorded_at)`

### `ml_forecasts`

| Column | Type | Description |
|--------|------|-------------|
| `fuel_type` | TEXT | Fuel type |
| `forecast_date` | DATE | Target date |
| `predicted_pence` | NUMERIC | SNARIMAX prediction |

### `ml_anomalies`

| Column | Type | Description |
|--------|------|-------------|
| `node_id` | TEXT | Station identifier |
| `fuel_type` | TEXT | Fuel type |
| `price_pence` | NUMERIC | Reported price |
| `lower_threshold` | NUMERIC | μ - 2σ |
| `upper_threshold` | NUMERIC | μ + 2σ |

### `ml_predictions`

| Column | Type | Description |
|--------|------|-------------|
| `node_id` | TEXT | Station identifier |
| `fuel_type` | TEXT | E10, E5, B7, SDV |
| `predicted_pence` | NUMERIC | XGBoost prediction |
| `brand_name` | TEXT | Station brand |
| `city` | TEXT | City |
| `county` | TEXT | County |
| `latitude` | NUMERIC | Lat |
| `longitude` | NUMERIC | Lon |

### `ingest_log`

| Column | Type | Description |
|--------|------|-------------|
| `ran_at` | TIMESTAMPTZ | Run timestamp |
| `rows_inserted` | INT | Rows upserted |
| `status` | TEXT | success / skipped / error |
| `kaggle_last_updated` | TEXT | Dataset freshness marker |
| `error_message` | TEXT | Error detail if failed |

---

## REST API Reference

**Base URL:** `https://ukfuel-ml.azurewebsites.net`
All endpoints: `GET`, no authentication required.

### Core Data

| Endpoint | Parameters | Description |
|----------|-----------|-------------|
| `GET /health` | — | API health check |
| `GET /prices` | `fuel_type`, `county`, `limit` | Raw price records |
| `GET /stations` | — | All station metadata |

### Statistics

| Endpoint | Parameters | Description |
|----------|-----------|-------------|
| `GET /stats/summary` | — | Today's national averages per fuel type |
| `GET /stats/national-average` | `period` (today\|7d\|30d\|90d), `region` (all\|england\|scotland\|wales\|ni) | Filtered national averages |
| `GET /stats/price-change` | — | Price delta vs 7 days and 30 days ago |
| `GET /stats/price-trend` | `days` (default 30, max 365) | Daily average per fuel type over N days |
| `GET /stats/by-county` | `fuel_type` | Average price ranked by county |
| `GET /stats/by-brand` | `fuel_type` | Average price and station count by brand |
| `GET /stats/by-day-of-week` | `fuel_type` | Average price by day of week |
| `GET /stats/by-month` | `fuel_type` | Monthly seasonality averages |
| `GET /stats/cheapest-stations` | `fuel_type`, `limit` | Cheapest stations today |
| `GET /stats/motorway-compare` | — | Motorway vs regular station price premium |
| `GET /stats/supermarket-compare` | — | Supermarket vs regular station discount |
| `GET /stats/distribution` | `fuel_type` | Price histogram bucket data |
| `GET /stats/station-count-by-county` | — | Station density per county |
| `GET /stats/status` | — | System status, last ingest time, record counts |

### ML Endpoints

| Endpoint | Parameters | Description |
|----------|-----------|-------------|
| `GET /forecast/{fuel_type}` | `horizon` (default 7, max 30) | SNARIMAX 7-day price forecast |
| `GET /anomalies` | `fuel_type` | Z-score flagged price anomalies |
| `GET /predict` | `node_id`, `fuel_type` | Single-station XGBoost prediction |
| `GET /stats/predicted-cheapest` | `fuel_type`, `limit` | Top N cheapest XGBoost predictions |

---

## Dashboard Features

The frontend renders 20+ interactive panels covering:

### Price Overview
- **National averages** — KPI tiles for all fuel types with period (Today / 7-day / 30-day / 90-day) and UK region filters (All UK / England / Scotland / Wales / N. Ireland)
- **Price change cards** — 7-day and 30-day delta with directional badges
- **30-day trend chart** — multi-series line chart for all fuel types simultaneously

### Pattern Analysis
- **Cheapest day of week** — bar chart showing which weekday averages lowest
- **Monthly seasonality** — line chart of average prices by calendar month
- **Price distribution** — histogram of price frequency buckets

### Geographic Analysis
- **Cheapest counties** — ranked table with inline progress bars
- **Most expensive counties** — ranked table (red header for intuitive coding)
- **Station density by county** — horizontal bar chart
- **Interactive map** — Leaflet.js map with colour-coded markers (green = cheap → red = expensive), filtered to UK bounding box

### Brand & Station Type
- **Average price by brand** — horizontal bar chart for top 15 brands
- **Brand market share** — doughnut chart by station count
- **Motorway vs regular** — grouped bar comparison
- **Supermarket vs regular** — grouped bar comparison

### ML Insights
- **SNARIMAX forecast** — 7-day line chart with confidence context
- **Anomaly alerts** — Z-score flagged stations with price and threshold range
- **XGBoost predictions** — top 10 predicted cheapest stations (top 3 rows highlighted)
- **Live price feed** — most recent 20 price updates

### UI/UX
- Glassmorphism card design with backdrop blur
- Hover aura animation cycling through brand palette colours
- Responsive grid layout (4-col → 2-col → 1-col)
- `localStorage` caching (30-min TTL, 24-hour stale fallback) for offline resilience
- Cache banner notification when serving stale data

---

## Deployment

### Frontend — GitHub Pages

- **URL:** `https://anandhu-bhaskar.github.io/UK-FuelPrices-Dashboard-With-Prediction/`
- **Trigger:** Auto-deploys on every push to `main`
- **Files served:** `frontend/` directory (HTML, CSS, JS)
- **No build step** — pure static files, zero dependencies to install

### REST API — Azure Functions (HTTP Trigger)

- **URL:** `https://ukfuel-ml.azurewebsites.net`
- **Plan:** Consumption (serverless — scales to zero, billed per execution)
- **Runtime:** Python 3.11
- **Route prefix:** empty (root-level routes)
- **CORS:** open (`*`) for public dashboard access
- **Function file:** `azure_function/api/`

### ML Training — Azure Functions (Timer Triggers)

All three training functions are deployed to the same Azure Functions app:

| Function | Schedule (UTC) | Runtime |
|----------|----------------|---------|
| SNARIMAX training | 1st & 15th at 02:00 | ~2–5 min |
| XGBoost training | 1st & 15th at 03:00 | ~5–10 min |
| Anomaly detection | 1st & 15th at 04:00 | ~1–2 min |

Training is staggered (1-hour gaps) to avoid database contention and memory pressure on the Consumption plan.

### Database — Neon PostgreSQL

- **Provider:** Neon (serverless PostgreSQL)
- **Plan:** Free tier
- **Connection:** Managed via `NEON_DB_URL` environment variable in Azure Functions settings
- **Features used:** Standard PostgreSQL 15, `ON CONFLICT DO NOTHING` upserts, window functions, date arithmetic

### Model Storage — Azure Blob Storage

- **Container:** `models`
- **Blob layout:** `{model_name}/latest.pkl` and `{model_name}/backup.pkl`
- **Purpose:** Decouples model training from the API process — the API loads trained models from Blob on cold start rather than retraining on each request

---

## Local Development

### Prerequisites

- Python 3.11+
- Node.js (optional — only for a local HTTP server)
- Azure Functions Core Tools v4
- Kaggle account with API key
- Neon PostgreSQL connection string

### 1. Clone the repository

```bash
git clone https://github.com/anandhu-bhaskar/UK-FuelPrices-Dashboard-With-Prediction.git
cd UK-FuelPrices-Dashboard-With-Prediction
```

### 2. Set up Python environment

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r azure_function/requirements.txt
pip install -r scripts/requirements.txt
```

### 3. Configure environment variables

Create `azure_function/local.settings.json`:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "<your-azure-storage-connection-string>",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "NEON_DB_URL": "<your-neon-postgres-connection-string>",
    "AZURE_STORAGE_CONNECTION_STRING": "<your-azure-storage-connection-string>",
    "KAGGLE_USERNAME": "<your-kaggle-username>",
    "KAGGLE_KEY": "<your-kaggle-api-key>"
  }
}
```

### 4. Run the data pipeline

```bash
cd scripts
python ingest.py
```

### 5. Start the Azure Functions locally

```bash
cd azure_function
func start
```

The API will be available at `http://localhost:7071`.

### 6. Serve the frontend

```bash
cd frontend
python -m http.server 8080
# Open http://localhost:8080
```

Update `frontend/js/api.js` to point to `http://localhost:7071` for local API calls.

---

## Project Structure

```
UK_FUEL_DASHBOARD/
│
├── frontend/                        # Static frontend (GitHub Pages)
│   ├── index.html                   # Single-page app shell
│   ├── css/
│   │   └── style.css                # Glassmorphism design system
│   └── js/
│       ├── api.js                   # API client with localStorage cache
│       └── dashboard.js             # All chart renders, state management
│
├── azure_function/                  # Azure Functions app
│   ├── host.json                    # Function app config (timeout, CORS, routes)
│   ├── requirements.txt             # Python dependencies
│   │
│   ├── api/                         # HTTP Trigger — REST API
│   │   ├── app.py                   # FastAPI application (20+ endpoints)
│   │   └── function.json            # Binding config
│   │
│   ├── snarimax_training/           # Timer Trigger — SNARIMAX forecast
│   │   └── __init__.py
│   │
│   ├── xgboost_training/            # Timer Trigger — XGBoost regression
│   │   └── __init__.py
│   │
│   ├── anomaly_training/            # Timer Trigger — Z-score detection
│   │   └── __init__.py
│   │
│   └── shared/                      # Shared utilities
│       ├── db.py                    # Neon PostgreSQL connection
│       └── model_store.py           # Azure Blob Storage model versioning
│
└── scripts/                         # Standalone scripts
    ├── ingest.py                    # Weekly ETL pipeline (Kaggle → Neon)
    └── requirements.txt
```

---

## Key Engineering Decisions

**Serverless everywhere** — Azure Functions Consumption plan and Neon serverless Postgres both scale to zero, keeping ongoing costs near zero for a data project with non-continuous traffic.

**Delta ingestion** — The ingest script checks Kaggle's `last_updated` metadata before downloading the full 200 MB dataset. If unchanged, it skips the download entirely and logs a `skipped` status. When a download is needed, it filters to only records newer than the DB's `MAX(recorded_at)` to avoid re-inserting millions of existing rows.

**Model backup versioning** — Before overwriting a trained model in Blob Storage, the existing artefact is promoted to `backup`. If a retraining run produces a broken model or the upload fails mid-way, the API falls back to the backup automatically, ensuring the dashboard never goes dark due to a training failure.

**Stale-while-revalidate caching** — The frontend caches every API response in `localStorage` keyed by URL. On each page load it tries the network first; if the Azure Function is cold-starting or unavailable, it serves the 24-hour-old cache and shows a banner. This gives a working dashboard even during the several-second cold-start latency of the Consumption plan.

**UK bounding-box filter** — Some station coordinates in the source data are invalid (e.g., lat 42° = Spain). The map renderer filters markers to `lat ∈ [49.5, 60.8]` and `lon ∈ [−8, 2]` in the browser, avoiding the need to clean the database.

**Fuel type normalisation** — The database stores canonical fuel type names (`B7_STANDARD`, `HVO`) matching the source dataset. The dashboard tabs use shorter user-facing codes (`B7`, `SDV`). A `DB_FUEL_MAP` object in `api.js` translates at the API call layer, keeping both the DB schema and UI labels clean.
