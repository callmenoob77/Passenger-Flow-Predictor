# Hecatron — Fog Copilot

A passenger rerouting system that helps travelers find alternative transport when flights are cancelled due to fog at Iași Airport (LRIA).

> The system checks your flight status. If your flight is at risk of fog or cancelled, it maps out alternative flights, trains, and buses — ranked by latency, price, and transfers.

---

## Architecture

```
frontend (React/Vite :5173)
    ↓ /api/*
rerouting API (FastAPI :8000)
    ↓ optional
ml service (FastAPI :8001)   ← fog risk prediction (LightGBM)
    ↓ optional
Supabase (PostgreSQL)        ← subscriptions & refund requests
```

**Demo mode** — the app runs fully without Supabase or the ML service. Flight lookups and rerouting work offline using the built-in database. Subscribe and refund endpoints silently succeed.

---

## Quick Start (local demo)

### Prerequisites
- Python 3.13 (standard CPython, not MSYS2/MinGW)
- Node.js 18+

### 1. Environment

```bash
cd hecatron
cp .env.example .env
# Edit .env only if you have Supabase / API keys. Leave blank for demo mode.
```

### 2. Backend

```bash
# Windows
.\venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

cd rerouting
uvicorn api:app --reload --port 8000
# API running at http://127.0.0.1:8000
```

If the venv is missing, recreate it:
```bash
# Windows (PowerShell)
py -3.13 -m venv venv
.\venv\Scripts\pip install -r rerouting\requirements.txt

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
pip install -r rerouting/requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
# App at http://localhost:5173
```

---

## Demo flights to try

| Flight | Route | Status |
|--------|-------|--------|
| `RO 6769` | Iași → Milano | FOG RISK |
| `OS 704` | Iași → Vienna | FOG RISK |
| `FR 3113` | Iași → Bergamo | FOG RISK |
| `RO 6771` | Iași → Londra | ON TIME |
| `RO 707` | Iași → București | ON TIME |

---

## Deploy to Render

The `render.yaml` at the repo root configures a web service for the backend.

1. Push this repo to GitHub
2. Create a new Render Web Service — connect the repo, Render detects `render.yaml` automatically
3. Set secret env vars in the Render dashboard:
   - `SUPABASE_CONN_STRING` (optional)
   - `SUPABASE_URL` / `SUPABASE_KEY` (optional, for email notifications)
   - `RESEND_API_KEY` (optional)
   - `ALLOWED_ORIGINS` — set to your Vercel frontend URL, e.g. `https://hecatron.vercel.app`
4. Deploy the frontend to Vercel/Netlify:
   - Set `VITE_API_BASE` env var to your Render backend URL (e.g. `https://hecatron-api.onrender.com`)
   - Build command: `npm run build`, output: `dist`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/flight/{flight_number}` | Flight details & fog risk status |
| `POST` | `/subscribe` | Register email for weather alerts |
| `POST` | `/refund` | Submit EU261 refund claim |
| `POST` | `/reroute` | Get ranked alternative transport options |

---

## Transport Adapters

Adapter pattern — each source implements the same interface. Failures are skipped.

| Adapter | Source | Data |
|---------|--------|------|
| `adapter_flixbus.py` | FlixBus public API | Real-time bus trips |
| `adapter_train.py` | CFR timetable (static) | Iași → București trains |
| `adapter_gflights_cached.py` | Pre-scraped Google Flights | 7 days cached flight data |

**Scoring** (lower = better):
```
score = 1.0 × arrival_lateness_hours + 0.05 × price_eur + 1.5 × transfers
```

---

## ML Service (fog prediction)

Located in `ml/`. Predicts `P(visibility < 1000m)` at 2h and 6h horizons using LightGBM + calibration.

```bash
cd ml
pip install -e ".[serve]"   # or: uv sync --extra serve
python train.py             # train model (requires historical METAR data)
uvicorn app:app --port 8001
```

The rerouting API calls the ML service at `ML_API_URL` (default `http://localhost:8001`). If it's not running, flight status falls back to the hardcoded `status` field in `flights_db.py`.

### ML Architecture
```
ingest → features → splits → model (LightGBM + calibration) → conformal → decision → FastAPI
```

---

## Data Pipeline

METAR weather observations for LRIA:

- `data-pipeline/backfill_metar.py` — load historical data into Supabase
- `data-pipeline/live_ingest.py` — periodic ingest (cron / GitHub Actions)
- `data-pipeline/create_subscriptions_table.py` — init subscriptions table
- `data-pipeline/create_refunds_table.py` — init refund claims table

---

## Frontend Screens

1. **Home** — enter flight number + email (subscribes to alerts)
2. **Flight Status** — route info, schedule, ON TIME / FOG RISK status
3. **Cancelled** — EU261 options: refund or find alternatives
4. **Alternatives** — ranked flights, buses, trains with prices and booking links
5. **Refund Claim** — submit passenger info and PNR for EU261 credits
