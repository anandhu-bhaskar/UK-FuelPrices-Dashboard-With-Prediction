# UK Fuel Price Dashboard & ML Prediction Engine

**Live Application:** [https://anandhu-bhaskar.github.io/UK-FuelPrices-Dashboard-With-Prediction/](https://anandhu-bhaskar.github.io/UK-FuelPrices-Dashboard-With-Prediction/)

**API Base URL:** [https://ukfuel-ml.azurewebsites.net](https://ukfuel-ml.azurewebsites.net)

---

[![Dashboard Demo](https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExYnU5amlsYTcwM2kybjVheno1a3BwNGtka2IwbjA4Nmo1Y3l1MTBqOCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Ql0qph2lFZmQzgesXB/giphy.gif)](https://www.awesomescreenshot.com/video/53428053?key=925a2addb4b4fcc6ed6f7be7b95df880)

---

A full-stack, cloud-deployed data engineering and machine learning project built around real-world UK fuel pricing data. The system ingests weekly price readings from thousands of UK filling stations, stores them in a cloud PostgreSQL database, trains three machine learning models on a biweekly schedule, and serves everything through a serverless REST API to an interactive browser dashboard.

All infrastructure is fully automated — data arrives without manual intervention, models retrain on a schedule, and every code push to `main` triggers a targeted deployment through GitHub Actions CI/CD.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Source](#data-source)
3. [Tech Stack](#tech-stack)
4. [CI/CD Pipeline — GitHub Actions](#cicd-pipeline--github-actions)
5. [Automated Data Pipeline](#automated-data-pipeline)
6. [Component Breakdown](#component-breakdown)
7. [Machine Learning Models & Continuous Learning](#machine-learning-models--continuous-learning)
8. [Database Schema](#database-schema)
9. [REST API Reference](#rest-api-reference)
10. [Dashboard Features](#dashboard-features)
11. [Deployment](#deployment)
12. [Local Development](#local-development)
13. [Project Structure](#project-structure)
14. [Key Engineering Decisions](#key-engineering-decisions)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Automated Data Pipeline                              │
│                                                                             │
│   GitHub Actions cron (every Monday 00:00 UTC)                             │
│         │                                                                   │
│         ▼                                                                   │
│   Kaggle API ──► ingest.py (freshness check → delta load) ──► Neon         │
│                  Python / pandas / psycopg2                    PostgreSQL   │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Azure Functions (Serverless — Python 3.11)               │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│  │  SNARIMAX        │  │   XGBoost        │  │  Z-score         │         │
│  │  Forecaster      │  │  Regression      │  │  Anomaly Det.    │         │
│  │  Timer Trigger   │  │  Timer Trigger   │  │  Timer Trigger   │         │
│  │  1st & 15th      │  │  1st & 15th      │  │  1st & 15th      │         │
│  │  02:00 UTC       │  │  03:00 UTC       │  │  04:00 UTC       │         │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘         │
│           │                     │                      │                   │
│           └─────────────────────┼──────────────────────┘                   │
│                                 ▼                                           │
│                   Azure Blob Storage (model versioning)                    │
│                   latest.pkl / backup.pkl per model                        │
│                                 │                                           │
│                   ┌─────────────▼─────────────┐                            │
│                   │    FastAPI REST API        │ ◄── HTTP GET requests     │
│                   │    HTTP Trigger            │                            │
│                   │    20+ endpoints           │                            │
│                   └───────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GitHub Pages (Frontend)                               │
│                                                                             │
│   Vanilla JS (ES Modules) + Chart.js 4.4 + Leaflet.js 1.9                 │
│   20+ interactive charts, geospatial map, ML insights                      │
│   localStorage cache (30-min TTL, 24-hour stale fallback)                 │
└─────────────────────────────────────────────────────────────────────────────┘
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
| SDV / HVO | Super diesel / Hydrogenated vegetable oil (renewable diesel) |
| B10 | High-biodiesel blend |

**Data Volume:** Millions of price readings across 6,000+ UK filling stations. Prices are validated between 100p–220p per litre during ingestion.

---

## Tech Stack

### Backend & Data Engineering

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.11 | Primary backend language |
| FastAPI | 0.115.0 | REST API framework (async, OpenAPI auto-docs) |
| Azure Functions | 1.21.3 | Serverless compute — HTTP + Timer triggers |
| pandas | 2.2.2 | Data manipulation, ETL pipeline |
| psycopg2 | 2.9.9 | PostgreSQL driver, `execute_values` bulk upserts |
| XGBoost | 2.0.3 | Gradient-boosted tree regression |
| scikit-learn | 1.4.2 | Label encoding, preprocessing |
| river | 0.21.2 | Online/incremental ML — SNARIMAX time-series forecasting |
| azure-storage-blob | 12.20.0 | Model artefact versioning (latest + backup blobs) |
| Kaggle API | — | Automated dataset download with freshness check |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| Vanilla JavaScript (ES Modules) | ES2022 | Dashboard logic, API client, state management |
| Chart.js | 4.4.0 | 15+ chart types (line, bar, doughnut, histogram) |
| Leaflet.js | 1.9.4 | Interactive geospatial station map |
| CSS3 (Glassmorphism) | — | Backdrop-blur cards, hover aura animations, responsive grid |
| Google Fonts — Space Grotesk | — | Typeface for header / primary navigation |

### Infrastructure

| Service | Provider | Purpose |
|---------|----------|---------|
| Serverless PostgreSQL | Neon | Primary database — scales to zero |
| Serverless Functions | Azure Functions (Consumption) | API + ML training — billed per execution |
| Blob Storage | Azure Storage | Trained model artefacts (latest / backup) |
| Static Hosting | GitHub Pages | Frontend CDN delivery |
| CI/CD | GitHub Actions | 3 automated workflows (see below) |
| Dataset Source | Kaggle | Weekly price data via API |

---

## CI/CD Pipeline — GitHub Actions

Three GitHub Actions workflows automate the entire deployment and data lifecycle. None of the deployments require manual `git push` to a separate deploy branch or manual CLI commands.

### 1. Frontend Deployment — `deploy_frontend.yml`

**Trigger:** Push to `main` branch with changes under `frontend/**` (path filter).  
**What it does:**

```
push to main (frontend/ changed)
   │
   ▼
checkout → configure-pages → upload-pages-artifact (frontend/ dir)
   │
   ▼
deploy-pages → live at https://anandhu-bhaskar.github.io/UK-FuelPrices-Dashboard-With-Prediction/
```

No build step is needed — the frontend is pure HTML/CSS/JS with no transpilation or bundling. The path filter ensures that backend commits (e.g., ML model changes) do not trigger an unnecessary frontend redeploy.

### 2. Azure Functions Deployment — `deploy_functions.yml`

**Trigger:** Push to `main` branch with changes under `azure_function/**` (path filter) or manual `workflow_dispatch`.  
**What it does:**

```
push to main (azure_function/ changed)
   │
   ▼
checkout → setup-python 3.11
   │
   ▼
pip install -r azure_function/requirements.txt
  --target azure_function/.python_packages/lib/site-packages
   │
   ▼
az login (service principal — client ID/secret stored in GitHub Secrets)
   │
   ▼
zip azure_function/ (excluding .pyc, __pycache__) → deploy.zip
   │
   ▼
az functionapp deployment source config-zip
  --name ukfuel-ml --resource-group uk-fuel-rg --src deploy.zip
   │
   ▼
live at https://ukfuel-ml.azurewebsites.net
```

Authentication uses a non-interactive Azure service principal (`az login --service-principal`) with credentials stored as GitHub repository secrets (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`). This avoids storing long-lived tokens and follows the principle of least privilege.

The path filter means that commits touching only `frontend/` (styling, chart tweaks) do not trigger a function app redeploy, and vice versa — keeping CI jobs fast and targeted.

### 3. Weekly Data Ingest — `weekly_ingest.yml`

**Trigger:** Scheduled cron `0 0 * * 1` (every Monday at 00:00 UTC) plus `workflow_dispatch` for manual runs.  
**What it does:**

```
Cron: every Monday 00:00 UTC
   │
   ▼
GitHub-hosted runner (ubuntu-latest)
   │
   ▼
checkout → setup-python 3.11 (pip cache enabled for requirements.txt)
   │
   ▼
pip install scripts/requirements.txt
   │
   ▼
python scripts/ingest.py
  ├── check Kaggle dataset freshness (metadata API — avoid 200 MB download if unchanged)
  ├── download dataset if new version exists
  ├── join stations + price history, engineer features
  ├── delta-load only new records (filtered by MAX(recorded_at) from DB)
  └── execute_values bulk upsert with ON CONFLICT DO NOTHING deduplication
   │
   ▼
results written to ingest_log table (rows inserted, status, timestamp)
```

All DB credentials (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) and Kaggle API keys (`KAGGLE_USERNAME`, `KAGGLE_KEY`) are injected as environment variables from GitHub Secrets — never hardcoded in the repository.

---

## Automated Data Pipeline

### How Data Flows from Kaggle to the Dashboard

```
Kaggle Dataset (jamesb7/fuel-prices-uk)
        │
        │  [Kaggle Python client — dataset API]
        ▼
scripts/ingest.py
   ├── 1. Freshness check: query Kaggle metadata for last_updated timestamp
   │      → if unchanged since last ingest_log entry: log "skipped", exit
   │      → avoids downloading 200 MB on every Monday run when data hasn't changed
   │
   ├── 2. Download & extract to temp dir
   │
   ├── 3. Feature engineering (pandas):
   │      join stations.csv → price_history.csv on node_id
   │      extract: year, month, day, day_of_week, hour from recorded_at
   │      validate: price_pence in [100, 220] range
   │      fill nulls: geography, brand_name → "Unknown"
   │
   ├── 4. Delta load:
   │      query DB: SELECT MAX(recorded_at) FROM fuel_prices
   │      filter dataset: only rows newer than that timestamp
   │      → typically 1–3 days of new readings per weekly run
   │
   ├── 5. Bulk upsert (psycopg2.extras.execute_values):
   │      INSERT INTO fuel_prices ... ON CONFLICT (node_id, fuel_type, recorded_at) DO NOTHING
   │      batch size: 1,000 rows per execute_values call
   │
   └── 6. Audit log:
          INSERT INTO ingest_log (ran_at, rows_inserted, status, kaggle_last_updated, error_message)
```

The delta load pattern is essential for efficiency: Kaggle's dataset can contain millions of historical rows, but only the newest records (typically a few thousand per week) need to be upserted on each run. The deduplication `ON CONFLICT DO NOTHING` ensures idempotent re-runs — if the job is re-triggered (e.g., via `workflow_dispatch`), no rows are duplicated.

---

## Component Breakdown

### 1. Data Ingestion Pipeline (`scripts/ingest.py`)

A Python ETL script that runs weekly via GitHub Actions cron to keep the database current:

- **Freshness check** — queries Kaggle's dataset metadata before downloading to skip unnecessary 200 MB pulls when data hasn't changed
- **Download** — uses the official Kaggle Python client to fetch and unzip the dataset to a temporary directory
- **Feature engineering** — joins station metadata to price records, extracts temporal features (`year`, `month`, `day`, `day_of_week`, `hour`), validates price ranges, fills null geographies
- **Delta load** — filters to only new records since the last successful ingest using `MAX(recorded_at)` from the DB
- **Bulk insert** — uses `psycopg2.extras.execute_values` for high-throughput batch insertion with `ON CONFLICT DO NOTHING` deduplication
- **Audit log** — writes every run result (rows inserted, status, Kaggle dataset timestamp, errors) to `ingest_log`

### 2. REST API (`azure_function/api/app.py`)

A FastAPI application deployed as an Azure Functions HTTP trigger. All endpoints are read-only (`GET`). CORS is open (`allow_origins=["*"]`). The API serves 20+ endpoints covering:

- Raw price and station data
- Aggregated statistics (by county, brand, day of week, month, distribution)
- ML model outputs (forecasts, anomalies, predictions)
- Comparative analyses (motorway vs regular, supermarket vs regular)
- Filtered national averages (time period × UK region) with period-over-period comparison using single-pass conditional SQL aggregation

See [REST API Reference](#rest-api-reference) for the full endpoint list.

### 3. ML Training Functions

Three Azure Functions Timer Triggers run biweekly (1st and 15th of each month at staggered UTC times to avoid database contention):

#### SNARIMAX Forecaster (`azure_function/snarimax_training/`)
Timer schedule: `0 0 2 1,15 * *` — **02:00 UTC** on the 1st and 15th.

#### XGBoost Regression (`azure_function/xgboost_training/`)
Timer schedule: `0 0 3 1,15 * *` — **03:00 UTC** on the 1st and 15th.

#### Z-score Anomaly Detector (`azure_function/anomaly_training/`)
Timer schedule: `0 0 4 1,15 * *` — **04:00 UTC** on the 1st and 15th.

### 4. Model Store (`azure_function/shared/model_store.py`)

Models are persisted to **Azure Blob Storage** with a `latest`/`backup` versioning pattern:

```
Before upload:
  models/{name}/latest.pkl  →  promoted to  →  models/{name}/backup.pkl

After upload:
  models/{name}/latest.pkl  ←  new trained model
  models/{name}/backup.pkl  ←  previous model (survives if upload fails)
```

On cold start, the API loads the model from Blob Storage (latest, falling back to backup). This decouples training from serving — the API never blocks on training, and a failed retraining run never takes the predictions offline.

### 5. Frontend Dashboard (`frontend/`)

A zero-framework, vanilla JavaScript single-page application built with ES modules. The API client (`js/api.js`) caches all responses in `localStorage` (30-minute TTL, 24-hour fallback) so the dashboard remains usable during Azure Function cold starts (typically 3–8 seconds on the Consumption plan).

---

## Machine Learning Models & Continuous Learning

All three models are retrained on the 1st and 15th of each month automatically via Azure Timer Triggers. No manual intervention is required. New data from the biweekly gap is incorporated into each retraining run.

### SNARIMAX — 7-Day Price Forecasting (Online/Incremental Learning)

**Library:** `river` (online/incremental ML)  
**Algorithm:** Seasonal Non-linear AutoRegressive Integrated Moving Average with eXogenous inputs (SNARIMAX)  
**Parameters:** `p=7, d=1, q=0, m=7` (7-day auto-regression, 1st-order differencing, weekly seasonality)

**How training works:**

```python
model = time_series.SNARIMAX(p=7, d=1, q=0, m=7)
for row in daily_national_averages.sort_values("date"):
    model.learn_one(x={}, y=float(row["mean_price"]))
```

Unlike batch models, `river`'s SNARIMAX uses **online learning** — it processes each observation exactly once and updates its internal state incrementally. This means the model is always "current" as of the latest training point and, in production, could be extended to learn from each arriving price reading in real time without storing the full history.

**Why SNARIMAX:**
- The price series shows clear **weekly periodicity** (prices tend to be cheaper mid-week than weekends). The `m=7` seasonal component captures this cycle.
- The differencing term `d=1` handles **non-stationarity** — petrol prices trend upward over years, so first-differencing converts the series to a stationary one before modelling.
- `p=7` means the model uses the previous 7 days as autoregressive inputs, capturing short-term momentum.
- SNARIMAX is trained **separately per fuel type** (E10, E5, B7_STANDARD, HVO etc.) so each fuel's unique seasonal pattern is preserved.

**Output:** 7-day ahead forecast stored in `ml_forecasts`, updated every retraining run.

**Continuous learning aspect:** On each biweekly retraining, the model replays the entire price history observation-by-observation (`learn_one` per day), then forecasts forward 7 days. As new weeks of real data accumulate, the model's parameters adapt to the latest price trends — if diesel prices spike due to an oil supply shock, the updated model's AR weights will reflect the new higher baseline within 2 weeks.

---

### XGBoost — Per-Station Price Regression (Biweekly Full Retrain)

**Library:** `xgboost`  
**Algorithm:** Gradient Boosted Decision Trees (regression)  
**Parameters:** `n_estimators=100, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8, tree_method=hist`

**Feature set (14 features):**

| Category | Features |
|----------|----------|
| Geospatial | `latitude`, `longitude` |
| Temporal | `year`, `month`, `day`, `day_of_week`, `hour` |
| Station flags | `is_motorway`, `is_supermarket`, `is_temporarily_closed`, `is_permanently_closed` |
| Categorical (label-encoded) | `fuel_type`, `brand_name`, `city`, `county` |

**How training works:**

```python
model = xgb.XGBRegressor(n_estimators=100, max_depth=6, ...)
model.fit(df[FEATURE_COLS], df["price_pence"])
# Applied to every station × fuel_type combination for inference
```

After training, the model is applied to every known station × fuel type combination (using the latest recorded temporal features) to produce predicted prices. These are stored in `ml_predictions`.

**Why XGBoost:**
- Handles **mixed numeric/categorical features** well without normalisation or one-hot encoding overhead.
- The `hist` tree method (histogram-based binning) is computationally efficient on large datasets with millions of rows.
- Gradient boosting captures **non-linear interactions** — e.g., a motorway Esso station in the south-east on a Monday morning has a predictably different price than a supermarket Asda in Wales on a Thursday.
- Categorical variables (brand, county) are label-encoded per feature column, with out-of-vocabulary values defaulting to `0`.

**Continuous learning aspect:** The model is retrained from scratch on the full dataset every 2 weeks. As new price data accumulates, the training set grows (more rows, more recent patterns) and the model's learned splits adjust to incorporate new price dynamics. New stations that appeared since the last training run are automatically included.

**Output:** Top-10 cheapest predicted stations per fuel type surfaced in the dashboard's XGBoost Predictions panel (top 3 rows highlighted with a teal tint).

---

### Z-score Anomaly Detection — Statistical Thresholding (Biweekly Recalibration)

**Algorithm:** Statistical Z-score thresholding per fuel type  
**Threshold:** ±2.0 standard deviations from the population mean

**How training works:**

```python
for fuel_type, group in df.groupby("fuel_type"):
    mean = group["price_pence"].mean()
    std  = group["price_pence"].std()
    thresholds[fuel_type] = {
        "lower_threshold": mean - 2.0 * std,
        "upper_threshold": mean + 2.0 * std,
    }
```

Any station reporting today's price outside `[μ − 2σ, μ + 2σ]` is flagged as anomalous and stored in `ml_anomalies`.

**Continuous learning aspect:** Thresholds are recalibrated biweekly against the full historical price distribution. This matters because the UK fuel price baseline shifts over time (e.g., a persistent oil price drop would lower the entire distribution, making what was "normal" months ago now statistically "high"). Without recalibration, the anomaly detector would produce stale false-positives. Thresholds are stored as JSON in Blob Storage (same latest/backup versioning as the other models).

**Output:** Anomaly alerts with price vs threshold range, displayed as alert cards in the ML Insights section.

---

### Model Versioning & Fault Tolerance

```
Retraining run on the 1st:

  1. Load existing model from Blob:  models/xgboost/latest.pkl
  2. Promote to backup:              models/xgboost/backup.pkl  ← safe copy
  3. Train new model on full data
  4. Upload new model:               models/xgboost/latest.pkl

  If step 4 fails (network error, OOM):
    models/xgboost/backup.pkl  still exists → API falls back, dashboard unaffected

  At cold start, API loads: latest.pkl → if missing: backup.pkl → if missing: 503
```

The API's `/forecast/{fuel_type}`, `/anomalies`, and `/stats/predicted-cheapest` endpoints return HTTP 503 with a clear message ("runs on 1st/15th") if no model has been trained yet — rather than crashing or returning corrupted data.

---

## Database Schema

**Database:** Neon PostgreSQL (serverless — connection pooling, scales to zero)

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
| `is_temporarily_closed` | INT | Station closure status |
| `is_permanently_closed` | INT | Station closure status |
| `brand_name` | TEXT | e.g. BP, Shell, Tesco |
| `city` | TEXT | City/town |
| `county` | TEXT | UK county |

**Primary key / unique constraint:** `(node_id, fuel_type, recorded_at)`

### `ml_forecasts`

| Column | Type | Description |
|--------|------|-------------|
| `fuel_type` | TEXT | Fuel type |
| `forecast_date` | DATE | Target date |
| `predicted_pence` | NUMERIC | SNARIMAX 7-day prediction |
| `computed_at` | TIMESTAMPTZ | Timestamp of the training run |

### `ml_anomalies`

| Column | Type | Description |
|--------|------|-------------|
| `node_id` | TEXT | Station identifier |
| `fuel_type` | TEXT | Fuel type |
| `price_pence` | NUMERIC | Reported price that triggered the flag |
| `lower_threshold` | NUMERIC | μ − 2σ |
| `upper_threshold` | NUMERIC | μ + 2σ |
| `detected_at` | TIMESTAMPTZ | Detection timestamp |

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
| `computed_at` | TIMESTAMPTZ | Timestamp of the training run |

### `ingest_log`

| Column | Type | Description |
|--------|------|-------------|
| `ran_at` | TIMESTAMPTZ | Run timestamp |
| `rows_inserted` | INT | Rows upserted this run |
| `status` | TEXT | success / skipped / error |
| `kaggle_last_updated` | TEXT | Dataset freshness marker |
| `error_message` | TEXT | Error detail if failed |

---

## REST API Reference

**Base URL:** `https://ukfuel-ml.azurewebsites.net`  
All endpoints: `GET`, no authentication required. CORS: `*`.

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
| `GET /stats/national-average` | `period` (today\|7d\|30d\|90d), `region` (all\|england\|scotland\|wales\|ni) | Filtered national averages with period-over-period comparison |
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

### Period-over-Period Comparison (`/stats/national-average`)

The `period` filter computes a current-window average alongside a prior-window average in a **single SQL pass** using conditional aggregation:

```sql
SELECT fuel_type,
  ROUND(AVG(CASE WHEN <current_window>  THEN price_pence END)::numeric, 2) AS avg_price,
  ROUND(AVG(CASE WHEN <previous_window> THEN price_pence END)::numeric, 2) AS prev_avg_price
FROM fuel_prices
WHERE <union_window>
GROUP BY fuel_type
HAVING AVG(CASE WHEN <current_window> THEN price_pence END) IS NOT NULL
```

| Period selected | Current window | Comparison window | Dashboard label |
|-----------------|---------------|-------------------|----------------|
| Today | Latest date in DB | 7 days prior | vs 7d ago |
| 7-day avg | Last 7 days | Days 8–14 ago | vs prev week |
| 30-day avg | Last 30 days | Days 31–60 ago | vs prev month |
| 90-day avg | Last 90 days | Days 91–180 ago | vs prev quarter |

---

## Dashboard Features

The frontend renders 20+ interactive panels covering:

### Price Overview
- **National averages** — KPI tiles for all fuel types with period (Today / 7-day / 30-day / 90-day) and UK region filters (All UK / England / Scotland / Wales / N. Ireland); badges show percentage delta against the prior equivalent window
- **Price change cards** — 7-day and 30-day delta with directional badges
- **30-day trend chart** — multi-series line chart for all fuel types simultaneously

### Pattern Analysis
- **Cheapest day of week** — bar chart showing which weekday averages lowest
- **Monthly seasonality** — line chart of average prices by calendar month
- **Price distribution** — histogram of price frequency buckets

### Geographic Analysis
- **Cheapest counties** — ranked table with inline progress bars
- **Most expensive counties** — ranked table (red header for intuitive visual coding)
- **Station density by county** — horizontal bar chart
- **Interactive map** — Leaflet.js map with colour-coded markers (green = cheap → red = expensive), filtered to UK bounding box

### Brand & Station Type
- **Average price by brand** — horizontal bar chart for top 15 brands
- **Brand market share** — doughnut chart by station count
- **Motorway vs regular** — grouped bar comparison
- **Supermarket vs regular** — grouped bar comparison

### ML Insights
- **SNARIMAX forecast** — 7-day line chart updated biweekly
- **Anomaly alerts** — Z-score flagged stations with price vs threshold range
- **XGBoost predictions** — top 10 predicted cheapest stations (top 3 rows highlighted)
- **Live price feed** — most recent 20 price updates from the DB

### UI/UX Design System
- Glassmorphism card design (`rgba(255,255,255,0.45)` + `backdrop-filter: blur(14px)`)
- Hover aura animation cycling through 7 brand palette colours (`@keyframes aura-cycle`)
- Brand design tokens — `--primary: #006E74`, `--warning: #C4571A`, `--amber: #A07840`, `--red: #B91C1C`
- Responsive grid layout (4-col → 2-col → 1-col breakpoints)
- `localStorage` caching (30-min TTL, 24-hour stale fallback) for offline resilience
- Cache banner notification when serving stale data

---

## Deployment

### Frontend — GitHub Pages

- **URL:** [https://anandhu-bhaskar.github.io/UK-FuelPrices-Dashboard-With-Prediction/](https://anandhu-bhaskar.github.io/UK-FuelPrices-Dashboard-With-Prediction/)
- **Trigger:** Push to `main` with changes in `frontend/` → GitHub Actions (`deploy_frontend.yml`)
- **Method:** `actions/upload-pages-artifact` + `actions/deploy-pages`
- **Files served:** `frontend/` directory (HTML, CSS, JS — no build step)

### REST API — Azure Functions (HTTP Trigger)

- **URL:** [https://ukfuel-ml.azurewebsites.net](https://ukfuel-ml.azurewebsites.net)
- **Plan:** Consumption (serverless — scales to zero, billed per execution)
- **Runtime:** Python 3.11
- **Trigger:** Push to `main` with changes in `azure_function/` → GitHub Actions (`deploy_functions.yml`) via Azure service principal
- **Resource group / app name:** `uk-fuel-rg` / `ukfuel-ml`

### ML Training — Azure Functions (Timer Triggers)

All three training functions are deployed to the same Azure Functions app as the REST API:

| Function | Cron schedule (UTC) | Estimated runtime |
|----------|---------------------|-------------------|
| SNARIMAX training | `0 0 2 1,15 * *` — 1st & 15th at 02:00 | ~2–5 min |
| XGBoost training | `0 0 3 1,15 * *` — 1st & 15th at 03:00 | ~5–10 min |
| Anomaly detection | `0 0 4 1,15 * *` — 1st & 15th at 04:00 | ~1–2 min |

Training is staggered (1-hour gaps) to avoid database contention and memory pressure on the Consumption plan.

### Database — Neon PostgreSQL

- **Provider:** Neon (serverless PostgreSQL)
- **Plan:** Free tier (scales to zero, autoscales on load)
- **Connection:** Managed via individual DB environment variables (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) injected at runtime in both Azure Functions settings and GitHub Actions secrets
- **SSL:** `sslmode=require` enforced on all connections

### Model Storage — Azure Blob Storage

- **Container:** `models`
- **Blob layout:** `{model_name}/latest.pkl` and `{model_name}/backup.pkl`
- **Access:** Connected via `AZURE_STORAGE_CONNECTION_STRING` environment variable
- **Purpose:** Decouples model training from the API — the API loads trained models on cold start rather than retraining on each request. Backup blobs ensure no prediction outage during a failed training run.

---

## Local Development

### Prerequisites

- Python 3.11+
- Node.js (optional — only for a local HTTP server)
- Azure Functions Core Tools v4
- Kaggle account with API key (`~/.kaggle/kaggle.json`)
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

Create `azure_function/local.settings.json` (never commit this file):

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "<your-azure-storage-connection-string>",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "DB_HOST": "<neon-hostname>.neon.tech",
    "DB_PORT": "5432",
    "DB_NAME": "<your-db-name>",
    "DB_USER": "<your-db-user>",
    "DB_PASSWORD": "<your-db-password>",
    "DB_SSL_MODE": "require",
    "AZURE_STORAGE_CONNECTION_STRING": "<your-azure-storage-connection-string>",
    "KAGGLE_USERNAME": "<your-kaggle-username>",
    "KAGGLE_KEY": "<your-kaggle-api-key>"
  }
}
```

For the ingest script, export the same DB and Kaggle variables as shell env vars, or set them in `scripts/.env`.

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
├── .github/
│   └── workflows/
│       ├── deploy_frontend.yml     # GitHub Pages — triggered on frontend/ changes
│       ├── deploy_functions.yml    # Azure Functions — triggered on azure_function/ changes
│       └── weekly_ingest.yml       # Data pipeline — cron every Monday 00:00 UTC
│
├── frontend/                       # Static frontend (GitHub Pages)
│   ├── index.html                  # Single-page app shell
│   ├── css/
│   │   └── style.css               # Glassmorphism design system, brand tokens, animations
│   └── js/
│       ├── api.js                  # API client with localStorage cache (30-min TTL)
│       └── dashboard.js            # Chart renders, state management, filter handlers
│
├── azure_function/                 # Azure Functions app
│   ├── host.json                   # Function app config (timeout, CORS, route prefix)
│   ├── requirements.txt            # Python dependencies
│   │
│   ├── api/                        # HTTP Trigger — REST API
│   │   ├── app.py                  # FastAPI application (20+ endpoints)
│   │   └── function.json           # HTTP binding config (anonymous auth, wildcard route)
│   │
│   ├── snarimax_training/          # Timer Trigger — SNARIMAX forecast (02:00 UTC)
│   │   ├── __init__.py             # train() + store_forecasts() + main()
│   │   └── function.json           # Cron: 0 0 2 1,15 * *
│   │
│   ├── xgboost_training/           # Timer Trigger — XGBoost regression (03:00 UTC)
│   │   ├── __init__.py             # train() + store_predictions() + main()
│   │   └── function.json           # Cron: 0 0 3 1,15 * *
│   │
│   ├── anomaly_training/           # Timer Trigger — Z-score detection (04:00 UTC)
│   │   ├── __init__.py             # train() + store_anomalies() + main()
│   │   └── function.json           # Cron: 0 0 4 1,15 * *
│   │
│   └── shared/                     # Shared utilities
│       ├── db.py                   # Neon PostgreSQL connection (psycopg2)
│       └── model_store.py          # Azure Blob Storage: save/load with latest/backup versioning
│
└── scripts/                        # Standalone ETL scripts
    ├── ingest.py                   # Weekly ETL pipeline: Kaggle → Neon (delta load)
    └── requirements.txt
```

---

## Key Engineering Decisions

**Serverless everywhere** — Azure Functions Consumption plan and Neon serverless Postgres both scale to zero, keeping ongoing costs near zero for a data project with non-continuous traffic.

**GitHub Actions path filters for targeted CI/CD** — The `deploy_frontend.yml` workflow only triggers when `frontend/**` changes; `deploy_functions.yml` only triggers on `azure_function/**` changes. This means a CSS change doesn't re-deploy the backend and vice versa, keeping pipeline jobs fast and reducing unnecessary Azure deployments.

**Delta ingestion with freshness check** — The ingest script checks Kaggle's `last_updated` metadata before downloading the full 200 MB dataset. If unchanged, it skips the download entirely and logs a `skipped` status. When a download is needed, it filters to only records newer than the DB's `MAX(recorded_at)` to avoid re-inserting millions of existing rows.

**Online learning via `river` SNARIMAX** — Rather than traditional batch ARIMA fitting (which requires storing and reprocessing the full time series), `river`'s SNARIMAX updates its internal state via `learn_one()` for each observation. This is architecturally aligned with streaming pipelines and is a design choice that scales naturally to real-time price feeds.

**Model backup versioning** — Before overwriting a trained model in Blob Storage, the existing artefact is promoted to `backup`. If a retraining run produces a broken model or the upload fails mid-way, the API falls back to the backup automatically, ensuring the dashboard never goes dark due to a training failure.

**Staggered ML training schedules** — The three Timer Triggers are offset by 1 hour each (02:00, 03:00, 04:00) to prevent concurrent DB reads during training, which could cause memory pressure on the Azure Consumption plan and query contention on Neon.

**Stale-while-revalidate caching** — The frontend caches every API response in `localStorage` keyed by URL. On each page load it tries the network first; if the Azure Function is cold-starting or unavailable, it serves the cached response and shows a banner. This gives a working dashboard even during the several-second cold-start latency of the Consumption plan.

**Single-pass conditional SQL aggregation** — The `/stats/national-average` endpoint computes both the current-period average and the prior-period average in a single SQL query using `CASE WHEN` conditional aggregation rather than two separate queries. This halves database round-trips and is more efficient on Neon's connection-per-query serverless model.

**UK bounding-box filter** — Some station coordinates in the source data are invalid (e.g., lat 42° = Spain). The map renderer filters markers to `lat ∈ [49.5, 60.8]` and `lon ∈ [−8, 2]` in the browser, avoiding the need to clean the database and keeping the ingest pipeline simple.

**Fuel type normalisation** — The database stores canonical fuel type names (`B7_STANDARD`, `HVO`) matching the source dataset. The dashboard tabs use shorter user-facing codes (`B7`, `SDV`). A `DB_FUEL_MAP` object in `api.js` translates at the API call layer, keeping both the DB schema and UI labels clean without requiring a transformation layer in the backend.
