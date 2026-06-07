# LRIA Fog-Disruption ML Engine

Visibility-below-minima risk prediction for Iași airport (LRIA) using LightGBM with
multi-station advection features, calibrated probabilities, and a tiered alert layer.

## What this predicts

The model outputs `P(visibility < THRESHOLD_M)` at configurable horizons (2 h, 6 h).
The target is a **visibility-risk proxy** — it is NOT a prediction of flight cancellations
or diversions, as no ground-truth cancellation records are available.

## Quick start

```bash
# Install deps
uv sync

# Download raw observations
python -m src.ingest

# Build features
python -m src.features

# Train and evaluate
python -m src.model

# Serve
uvicorn src.service:app --reload
```

## Adding a station

Edit `src/config.py` — add the ICAO code to `StationConfig.neighbours`. No code change required.

## Changing the fog threshold

Edit `FOG_THRESHOLD_M` in `src/config.py`. Labels are recomputed on the next feature build.

## Architecture

```
ingest → features → splits → model (LightGBM + calibration) → conformal → decision → FastAPI
```

Baselines: Logistic Regression + persistence (last observed visibility).
