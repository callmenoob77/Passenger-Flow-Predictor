# Hecatron — Fog Copilot

> 🏆 Built at **[Air Hack Iași](https://fablabiasi.ro/air-hack-iasi/)** (Heckatron hackathon) for the **Passenger Flow Predictor** challenge.

Fog is the single biggest disruptor at Iași Airport (LRIA). During peak hours, gate closures trigger cascading delays, passengers miss connections, and staff allocation is purely reactive. **Hecatron** flips this: it predicts fog-related flight disruptions **2 hours in advance**, automatically alerts affected passengers by email, and surfaces ranked alternative transport options — so both passengers and airport staff can act before the problem escalates.

---

## Screenshots

| Home | Flight Status | Cancelled |
|------|--------------|-----------|
| ![Home](screenshots/01-home.png) | ![Flight Status](screenshots/02-flight-status.png) | ![Cancelled](screenshots/03-cancelled.png) |

| Alternatives | Refund Claim | On Time |
|-------------|--------------|---------|
| ![Alternatives](screenshots/04-alternatives.png) | ![Refund](screenshots/05-refund.png) | ![On Time](screenshots/06-on-time.png) |

---

## What it does

1. **Predicts fog risk** at LRIA using a calibrated decision-tree ensemble (scikit-learn BaggingClassifier) trained on historical METAR weather observations from Iași and three neighbouring airports. Outputs a calibrated probability (0–100%) with an uncertainty band and a tiered alert level (full_risk / early_warning / silent) for a 2-hour horizon.
2. **Monitors flights** — passengers subscribe with their flight number and email. A departure-aware notifier emails each subscriber once, **`ALERT_LEAD_H` hours (default 2) before their flight departs**, if the flight is cancelled/delayed on the airport board or the fog model fires (needs `SUPABASE_CONN_STRING` + `RESEND_API_KEY` on the rerouting API). Flight data is resolved live, best source first:
   1. **Iași airport departures board** (the airport's own public API — free, no key, no quota; real status incl. delayed/cancelled and real departure times)
   2. **AviationStack** (any flight worldwide; optional `AVIATIONSTACK_API_KEY`)
   3. **Built-in demo flight DB** (always works, fully offline)
3. **Recommends alternatives** — rerouting engine queries real-time buses (FlixBus), CFR trains, cached flights, and **flights from nearby airports** (Bacău, Suceava, Chișinău — each paired with a real FlixBus/CFR ground leg from Iași that makes the departure), ranks everything by a latency-price-transfers score, and returns booking links.
4. **Supports EU 261/2004 refund claims** — passengers can submit refund requests directly through the app.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Frontend  (React + TypeScript + Vite)        │
│  Home → Flight Status → Cancelled → Alternatives → Refund   │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP /api/*
┌───────────────────────▼─────────────────────────────────────┐
│            Rerouting API  (FastAPI :8000)                    │
│  flight lookup · rerouting · subscriptions · refund claims  │
└───────────┬───────────────────────┬─────────────────────────┘
            │ ML_API_URL (optional) │ DB (optional)
┌───────────▼──────────┐  ┌────────▼──────────────────────────┐
│  ML Service           │  │  Supabase (PostgreSQL)            │
│  (FastAPI :8001)      │  │  metar_raw · subscriptions        │
│  Bagged-tree ensemble │  │  refund_claims                    │
└──────────────────────┘  └───────────────────────────────────┘
            ▲
            │ METAR feed (every 15 min via GitHub Actions)
┌───────────┴──────────────────────────────────────────────────┐
│  Data Pipeline  (GitHub Actions)                              │
│  Aviation Weather Center → Supabase                          │
│  Model retrain: weekly (Monday 03:00 UTC)                    │
└───────────────────────────────────────────────────────────────┘
```

**Demo mode** — the app runs fully without Supabase or the ML service. Flight lookups and rerouting work offline via a built-in flight database.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript, Vite |
| Rerouting API | Python 3.12+, FastAPI, Uvicorn |
| ML service | scikit-learn (bagged decision trees), pandas, FastAPI |
| Database | Supabase (PostgreSQL) |
| Email alerts | Resend |
| MLOps | GitHub Actions (ingest every 15 min, retrain weekly) |
| Hosting | Render (backend) + Vercel (frontend) |

---

## ML Pipeline

```
METAR ingest (IEM ASOS, 4 stations) → feature engineering
    → chronological split (60% train / 20% calibration / 20% test)
    → BaggingClassifier (200 class-balanced decision trees)
    → isotonic calibration (mean + p10/p90 → uncertainty band)
    → recall-targeted alert thresholds (full_risk / early_warning / silent)
    → FastAPI inference endpoint (/predict_fog, /run)
```

**Features** (30): visibility, temperature, dew point, dew-point depression (spread), Magnus relative humidity, wind speed/direction (circular encoding), hourly/seasonal cyclical encoding, plus the same signals from three neighbouring stations (LRSV, LRBC, LUKK) as fog-advection indicators.

**Target**: `fog_in_2h` — binary, fog at T+2h defined as `visibility < 1000 m` or `FG` in the weather codes.

**Evaluation**: held-out test metrics (recall/precision/F1 per tier, Brier score, CI width) are written to `ml/models/meta.json` on every retrain.

---

## How to run locally

### Prerequisites
- Python 3.12+ (standard CPython, not MSYS2/MinGW)
- Node.js 18+

### 1. Clone & configure environment

```bash
git clone https://github.com/callmenoob77/Fog-Disruptor.git
cd Fog-Disruptor
cp .env.example .env
# Leave .env blank for demo mode (no Supabase or ML service required).
# Fill in keys only if you want full functionality (see Environment Variables below).
```

### 2. Start the rerouting backend

```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate
pip install -r rerouting/requirements.txt

# Windows (PowerShell)
py -3.12 -m venv venv
.\venv\Scripts\activate
pip install -r rerouting\requirements.txt

# Then start the server (from repo root, venv active):
cd rerouting
uvicorn api:app --reload --port 8000
# → http://127.0.0.1:8000
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### 4. (Optional) Start the ML fog prediction service

```bash
cd ml
pip install -e ".[serve]"        # or: uv sync --extra serve
python train.py                  # requires Supabase METAR data (see Data Pipeline)
uvicorn app:app --port 8001
# → http://127.0.0.1:8001
```

The rerouting API automatically falls back to static flight status when the ML service is not running.

---

## Demo flights

> Any real Iași departure works out of the box — looked up live on the airport's departures board (no key needed). With `AVIATIONSTACK_API_KEY` set, non-Iași flights work too. The flights below are always available, even fully offline:

| Flight | Route | Status |
|--------|-------|--------|
| `RO 6769` | Iași → Milano | FOG RISK |
| `OS 704` | Iași → Vienna | FOG RISK |
| `FR 3113` | Iași → Bergamo | FOG RISK |
| `RO 6771` | Iași → Londra | ON TIME |
| `RO 707` | Iași → București | ON TIME |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/flight/{flight_number}` | Flight details + fog risk status |
| `POST` | `/subscribe` | Register email for fog alerts |
| `POST` | `/refund` | Submit EU 261/2004 refund claim |
| `POST` | `/reroute` | Get ranked alternative transport options |

**Rerouting score** (lower = better):
```
score = 1.0 × arrival_lateness_hours + 0.05 × price_eur + 1.5 × transfers
```

Transport adapters: FlixBus (real-time), CFR trains (static timetable: Iași → Bucharest / Bacău / Suceava), Google Flights (7-day cache), and nearby-airport flights (live departures from Bacău BCM, Suceava SCV and Chișinău KIV via AviationStack, combined with a FlixBus/CFR ground leg from Iași that arrives ≥ 1.5 h before the flight). Adapter failures are silently skipped; identical journeys from different adapters are deduplicated.

**Reachability rules** (fog scenario): every flight from another airport must be physically catchable — 1 h passenger reaction + real ground travel time + 1.5 h check-in. Flights from the disrupted airport itself are only offered after a 6 h fog-clearing window, and carry a "verify fog has cleared" note.

---

## Data Pipeline

METAR observations are fetched from [Aviation Weather Center](https://aviationweather.gov/api/data/metar) and stored in Supabase.

```bash
# One-time backfill (requires SUPABASE_CONN_STRING in .env)
python data-pipeline/backfill_metar.py

# Init DB tables
python data-pipeline/create_subscriptions_table.py
python data-pipeline/create_refunds_table.py
```

GitHub Actions automates everything in production:
- **`ingest.yml`** — runs every 15 minutes, ingests latest METAR, triggers ML prediction
- **`train_model.yml`** — runs every Monday at 03:00 UTC, retrains the model and commits updated artifacts

---

## Deploy to Render + Vercel

### Backend (Render)
1. Push the repo to GitHub
2. Create a new Render Web Service — `render.yaml` is auto-detected
3. Set environment variables in the Render dashboard (see below)

### Frontend (Vercel)
- Build command: `npm run build`
- Output directory: `dist`
- Set `VITE_API_BASE` to your Render backend URL

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_CONN_STRING` | No | PostgreSQL connection string for Supabase |
| `SUPABASE_URL` | No | Supabase project URL (email notifications) |
| `SUPABASE_KEY` | No | Supabase anon/service key |
| `RESEND_API_KEY` | No | [Resend](https://resend.com) key for email alerts |
| `AVIATIONSTACK_API_KEY` | No | [AviationStack](https://aviationstack.com) key — adds live lookup of non-Iași flights and live rerouting via Bacău/Suceava/Chișinău departures (Iași lookups already work via the airport board, no key needed) |
| `LRIA_BOARD_URL` | No | Override/disable the Iași airport board API (default: `https://www.aeroport-iasi.ro:5000`; set empty to disable) |
| `ML_API_URL` | No | URL of the ML service (default: `http://localhost:8001`) |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins for the backend |
| `VITE_API_BASE` | No (frontend) | Backend URL used by the React app |

All variables are optional for local demo mode.

---

## Project Structure

```
Fog-Disruptor/
├── frontend/          # React + TypeScript UI
│   └── src/screens/   # 5 screens: home, status, cancelled, alternatives, refund
├── rerouting/         # FastAPI rerouting API + transport adapters
├── ml/                # ML fog prediction service
│   ├── src/           # ingest · features · splits · model · conformal · decision
│   ├── train.py       # training entry point
│   ├── app.py         # FastAPI inference service (live METAR enrichment)
│   └── models/        # serialised LightGBM model artifacts
├── data-pipeline/     # METAR ingestion scripts + DB schema
└── .github/workflows/ # MLOps automation (ingest + retrain)
```

---

## License

MIT — see [LICENSE](LICENSE).
