# ✈️ Hecatron — Fog Copilot

A smart passenger rerouting system that helps travellers find alternative transport when flights get cancelled due to fog at Iasi Airport (LRIA).

> **How it works:** The system monitors real-time METAR weather data, predicts fog disruptions, and — when a flight is cancelled — instantly finds the best alternative routes via other flights, buses (FlixBus), or trains (CFR), ranked by arrival time, cost, and number of transfers.

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  data-pipeline   │     │    rerouting     │     │    frontend      │
│  METAR weather   │────▸│  FastAPI + 3     │◂────│  React + Vite    │
│  ingestion       │     │  adapters        │     │  4-screen flow   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              ▲
                        ┌─────┴─────┐
                        │   model    │
                        │ LightGBM   │
                        │ (planned)  │
                        └───────────┘
```

| Directory | What it does |
|---|---|
| `data-pipeline/` | Ingests METAR weather observations from [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/) into a Supabase PostgreSQL database — both historical backfill (3 years) and live updates every 15 minutes via GitHub Actions. |
| `rerouting/` | FastAPI backend with a resolver that queries 3 transport adapters (FlixBus API, CFR train timetable, Google Flights cache), scores alternatives, and returns the best options. |
| `model/` | ML model for fog/delay prediction using LightGBM *(in progress — not yet integrated)*. |
| `frontend/` | React + Vite + TypeScript app with a 4-screen user flow: enter flight → see status → flight cancelled → view ranked alternatives. |

---

## 🚀 Quick Setup

### Backend (Rerouting API)

```bash
cd rerouting
pip install -r requirements.txt
# Make sure your virtual environment is active (e.g. source ../venv/bin/activate)
python3 -m uvicorn api:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Try `GET /health` to verify.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`. The Vite dev server proxies `/api/*` requests to the backend automatically.

### Both together

Run the backend and frontend in two separate terminals. The frontend expects the backend on port `8000`.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/flight/{flight_number}` | Look up a flight from the demo database (e.g. `RO-6769`, `W6-2345`, `FR-4321`) |
| `POST` | `/reroute` | Given a cancelled flight, returns ranked alternative routes |

### Example: Get alternatives

```bash
curl -X POST http://localhost:8000/reroute \
  -H "Content-Type: application/json" \
  -d '{"origin_city":"Iasi","origin_icao":"LRIA","dest_city":"Milano","dest_icao":"MXP","scheduled_departure":"2026-06-10T08:00:00"}'
```

---

## 🔌 Transport Adapters

The rerouting engine uses a plug-and-play **adapter pattern** — each transport source implements the same interface. If one adapter fails (API down, no key), it's skipped and the rest still work.

| Adapter | Source | Data |
|---|---|---|
| `adapter_flixbus.py` | FlixBus public API (no key needed) | Real-time bus trips with prices |
| `adapter_train.py` | Static CFR timetable (hardcoded) | Iasi → Bucharest trains |
| `adapter_gflights_cached.py` | Pre-scraped Google Flights JSON | 7 days of cached flight data |

### Scoring

Alternatives are ranked by a weighted score *(lower = better)*:

```
score = 1.0 × arrival_lateness_hours + 0.05 × price_eur + 1.5 × transfers
```

Options departing less than **1 hour** after the cancelled flight are filtered out (the passenger needs time to react). Ground transport over **10 hours** is also removed.

---

## 🖥️ Frontend Screens

1. **Home** — Enter your flight number and email for alerts
2. **Flight Status** — See if your flight has fog risk, with an ad banner for partner services
3. **Flight Cancelled** — EU261 options: request refund or view rerouting alternatives
4. **Alternatives** — Ranked cards showing flights, buses, and trains with prices, times, and booking links

---

## 🌦️ Data Pipeline

The system ingests METAR weather observations for Iasi Airport (LRIA):

- **`backfill_metar.py`** — One-time script to load 3 years of historical data
- **`live_ingest.py`** — Runs every 15 minutes via GitHub Actions to keep data fresh

Data source: [Iowa Environmental Mesonet (IEM)](https://mesonet.agron.iastate.edu/)

---

## ⚙️ Environment Variables

| Variable | Usage | Required by |
|---|---|---|
| `DB_URL` | PostgreSQL connection string (Supabase) | `data-pipeline/` |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS v4 |
| Backend | Python, FastAPI, Pydantic |
| Database | PostgreSQL (Supabase) |
| Data | pandas, psycopg2, requests |
| ML *(planned)* | LightGBM |
| CI/CD | GitHub Actions |
