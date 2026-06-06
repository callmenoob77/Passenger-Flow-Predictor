# Hecatron

Passenger rerouting system for cancelled flights.

## Project Structure

| Directory | Contents |
|---|---|
| `data-pipeline/` | METAR ingestion (backfill + live) |
| `rerouting/` | FastAPI API + alternative adapters (FlixBus, train, flights) |
| `model/` | ML delay prediction model (LightGBM, in progress) |
| `frontend/` | React application |

## Quick Setup

```bash
cd rerouting
pip install -r requirements.txt
uvicorn api:app --reload
```

## Required Environment Variables

| Variable | Usage |
|---|---|
| `DB_URL` | PostgreSQL connection for METAR data |
