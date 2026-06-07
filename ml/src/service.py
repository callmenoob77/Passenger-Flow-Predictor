from __future__ import annotations

"""FastAPI inference service — loads trained model and exposes /predict endpoint."""

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.config import HORIZONS, get_config, setup_logging
from src.decision import classify_alert
from src.model import load_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# App

app = FastAPI(
    title       = "LRIA Fog Predictor",
    description = "Calibrated fog probability + tier alert for Iași airport",
    version     = "1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_MODEL_DIR = Path(os.getenv("MODEL_DIR", "models"))
_FEATURES_PATH = _MODEL_DIR / "features_latest.parquet"

# Lazy caches
_models:   dict[str, object]      = {}
_features: pd.DataFrame | None    = None


def _get_model(horizon: str):
    if horizon not in _models:
        path = _MODEL_DIR / f"lgb_fog_in_{horizon}.pkl"
        if not path.exists():
            raise HTTPException(
                status_code=503,
                detail=f"Model not found at {path}. Run: uv run python train.py",
            )
        _models[horizon] = load_model(str(path))
    return _models[horizon]


def _get_features() -> pd.DataFrame:
    global _features
    if _features is None:
        if not _FEATURES_PATH.exists():
            raise HTTPException(
                status_code=503,
                detail=f"Feature matrix not found at {_FEATURES_PATH}. Run: uv run python train.py",
            )
        _features = pd.read_parquet(_FEATURES_PATH)
        logger.info("Loaded feature matrix: %s rows x %s cols", *_features.shape)
    return _features


# ---------------------------------------------------------
# Schema

class PredictRequest(BaseModel):
    horizon:        str         = Field("2h",  description="Forecast horizon: '2h' or '6h'")
    visibility_m:   float | None = Field(None, description="Override current visibility (m)")
    temperature_c:  float | None = Field(None, description="Override temperature (°C)")
    dewpoint_c:     float | None = Field(None, description="Override dewpoint (°C)")
    wind_speed_mps: float | None = Field(None, description="Override wind speed (m/s)")
    wind_dir_deg:   float | None = Field(None, description="Override wind direction (deg)")


class PredictResponse(BaseModel):
    horizon:      str
    observed_at:  str
    prob:         float = Field(..., description="P(fog) in [0,1]")
    prob_lo:      float = Field(..., description="Lower conformal CI bound")
    prob_hi:      float = Field(..., description="Upper conformal CI bound")
    alert:        str   = Field(..., description="'strong' | 'soft' | 'silent'")


# ---------------------------------------------------------
# Endpoints

@app.get("/health")
def health():
    return {"status": "ok", "loaded_models": list(_models.keys())}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    cfg = get_config()

    if req.horizon not in HORIZONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown horizon '{req.horizon}'. Choose from {list(HORIZONS)}.",
        )

    # Ia cel mai recent rand din feature matrix
    features = _get_features()
    row = features.iloc[[-1]].copy()
    observed_at = str(features.index[-1])

    # Suprascrie campurile trimise explicit — doar daca exista ca coloana in feature matrix
    def _set(col: str, val: float) -> None:
        if col in row.columns:
            row[col] = val

    if req.visibility_m   is not None: _set("visibility_m",   req.visibility_m)
    if req.temperature_c  is not None: _set("temperature_c",  req.temperature_c)
    if req.dewpoint_c     is not None: _set("dewpoint_c",     req.dewpoint_c)
    if req.wind_speed_mps is not None: _set("wind_speed_mps", req.wind_speed_mps)
    if req.wind_dir_deg   is not None:
        wd = req.wind_dir_deg
        _set("wind_dir_sin", float(np.sin(np.radians(wd))))
        _set("wind_dir_cos", float(np.cos(np.radians(wd))))

    model = _get_model(req.horizon)

    # Conformal wrapper returneaza (p, lo, hi); altfel banda fixa
    if hasattr(model, "predict") and callable(model.predict):
        try:
            p, lo, hi = model.predict(row)
            prob = float(p[0]); lo = float(lo[0]); hi = float(hi[0])
        except Exception:
            prob = float(model.predict_proba(row)[0])
            lo   = max(0.0, prob - 0.1)
            hi   = min(1.0, prob + 0.1)
    else:
        prob = float(model.predict_proba(row)[0])
        lo   = max(0.0, prob - 0.1)
        hi   = min(1.0, prob + 0.1)

    alert = classify_alert(prob, cfg.tiers)

    return PredictResponse(
        horizon     = req.horizon,
        observed_at = observed_at,
        prob        = round(prob, 4),
        prob_lo     = round(lo,   4),
        prob_hi     = round(hi,   4),
        alert       = alert.value,
    )


# ---------------------------------------------------------
# Dev entrypoint

if __name__ == "__main__":
    import uvicorn
    setup_logging()
    uvicorn.run("src.service:app", host="0.0.0.0", port=8000, reload=False)
