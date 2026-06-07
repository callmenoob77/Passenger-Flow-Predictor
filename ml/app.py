"""FastAPI inference service — fog nowcasting with live NOAA neighbor enrichment."""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
_RESEND_KEY   = os.environ.get("RESEND_API_KEY", "")
_EMAIL_FROM   = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")

# ---------------------------------------------------------
# Config
# ---------------------------------------------------------
MODEL_DIR         = Path("models")
NEIGHBOR_STATIONS = ("LRSV", "LRBC", "LUKK")
NOAA_URL          = "https://aviationweather.gov/api/data/metar"

# ---------------------------------------------------------
# App
# ---------------------------------------------------------
app = FastAPI(
    title       = "LRIA Fog Predictor",
    description = "Calibrated fog probability + dynamic CI for Iași airport",
    version     = "2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Lazy-loaded model artifacts
# ---------------------------------------------------------
_cache: dict = {}


def _load_artifacts():
    """Load all model artifacts on first call."""
    if _cache:
        return

    for name in ("ensemble", "calibrator", "calibrator_lo", "calibrator_hi"):
        path = MODEL_DIR / f"{name}.pkl"
        if not path.exists():
            raise HTTPException(
                status_code=503,
                detail=f"Model artifact not found: {path}. Run: python train.py",
            )
        _cache[name] = joblib.load(path)

    meta_path = MODEL_DIR / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=503, detail="meta.json not found. Run: python train.py")
    with open(meta_path) as f:
        _cache["meta"] = json.load(f)

    cols_path = MODEL_DIR / "feature_cols.json"
    if not cols_path.exists():
        raise HTTPException(status_code=503, detail="feature_cols.json not found. Run: python train.py")
    with open(cols_path) as f:
        _cache["feature_cols"] = json.load(f)

    logger.info("Loaded model artifacts: %d features, thresholds: early=%.2f full=%.2f",
                len(_cache["feature_cols"]),
                _cache["meta"]["threshold_early_warning"],
                _cache["meta"]["threshold_full_risk"])


# ---------------------------------------------------------
# Schema (OBLIGATORY — exact as specified)
# ---------------------------------------------------------

class PredictRequest(BaseModel):
    horizon:        str        = Field("2h",  description="Forecast horizon")
    visibility_m:   int        = Field(...,   description="Current visibility in metres")
    temperature_c:  float      = Field(...,   description="Temperature in Celsius")
    dewpoint_c:     float      = Field(...,   description="Dewpoint in Celsius")
    wind_speed_mps: float      = Field(...,   description="Wind speed in m/s")
    wind_dir_deg:   int        = Field(...,   description="Wind direction in degrees")
    flight_code:    str | None = Field(None,  description="Optional flight code (pass-through)")


class PredictResponse(BaseModel):
    horizon:      str
    observed_at:  str
    prob:         float      = Field(..., description="P(fog) calibrated")
    prob_lo:      float      = Field(..., description="Lower CI (p10 calibrated)")
    prob_hi:      float      = Field(..., description="Upper CI (p90 calibrated)")
    alert:        str        = Field(..., description="'full_risk' | 'early_warning' | 'silent'")
    flight_code:  str | None = Field(None, description="Echo of input flight code")


# ---------------------------------------------------------
# NOAA AviationWeather live fetch
# ---------------------------------------------------------

def _fetch_noaa_neighbors() -> dict[str, dict]:
    """Fetch latest METAR from NOAA for neighbor stations.

    Returns dict: station_id -> {temperature_c, dewpoint_c, visibility_m, wind_speed_mps, wind_dir_deg, humidity_pct}
    """
    result = {}
    try:
        ids = ",".join(NEIGHBOR_STATIONS)
        resp = httpx.get(
            NOAA_URL,
            params={"ids": ids, "format": "json", "hours": 3},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            return result

        # Group by station, take most recent
        by_station: dict[str, list] = {}
        for obs in data:
            icao = obs.get("icaoId", "")
            if icao in NEIGHBOR_STATIONS:
                by_station.setdefault(icao, []).append(obs)

        for station, reports in by_station.items():
            # Take the most recent report
            latest = reports[0]  # NOAA returns newest first

            temp_c = latest.get("temp")
            dewp_c = latest.get("dewp")
            wdir   = latest.get("wdir")
            wspd   = latest.get("wspd")  # knots from NOAA
            vis_mi = latest.get("visib")  # statute miles

            parsed = {}
            if temp_c is not None:
                parsed["temperature_c"] = float(temp_c)
            if dewp_c is not None:
                parsed["dewpoint_c"] = float(dewp_c)
            if vis_mi is not None:
                parsed["visibility_m"] = float(vis_mi) * 1609.344
            if wspd is not None:
                parsed["wind_speed_mps"] = float(wspd) * 0.514444
            if wdir is not None:
                try:
                    parsed["wind_dir_deg"] = float(wdir)
                except (ValueError, TypeError):
                    pass

            # Compute humidity if temp and dewpoint available
            if "temperature_c" in parsed and "dewpoint_c" in parsed:
                t, td = parsed["temperature_c"], parsed["dewpoint_c"]
                a, b = 17.27, 237.7
                gamma_t  = (a * t) / (b + t)
                gamma_td = (a * td) / (b + td)
                parsed["humidity_pct"] = min(100.0, max(0.0, 100.0 * math.exp(gamma_td - gamma_t)))

            if parsed:
                result[station] = parsed

    except Exception as exc:
        logger.warning("NOAA fetch failed (non-critical, using fallback): %s", exc)

    return result


# ---------------------------------------------------------
# Feature assembly
# ---------------------------------------------------------

def _build_feature_row(req: PredictRequest, neighbors: dict[str, dict]) -> pd.DataFrame:
    """Assemble the feature vector matching training feature order."""
    _load_artifacts()
    feature_cols = _cache["feature_cols"]
    now = datetime.now(tz=timezone.utc)

    row = {}

    # Primary LRIA features
    row["visibility_m"]   = float(req.visibility_m)
    row["temperature_c"]  = float(req.temperature_c)
    row["dewpoint_c"]     = float(req.dewpoint_c)
    row["wind_speed_mps"] = float(req.wind_speed_mps)

    # Spread (dewpoint depression)
    row["spread"] = req.temperature_c - req.dewpoint_c

    # Humidity via Magnus formula
    t, td = req.temperature_c, req.dewpoint_c
    a, b = 17.27, 237.7
    gamma_t  = (a * t) / (b + t)
    gamma_td = (a * td) / (b + td)
    row["humidity_magnus"] = min(100.0, max(0.0, 100.0 * math.exp(gamma_td - gamma_t)))

    # Wind direction sin/cos
    wd_rad = math.radians(float(req.wind_dir_deg))
    row["wind_dir_sin"] = math.sin(wd_rad)
    row["wind_dir_cos"] = math.cos(wd_rad)

    # Hour sin/cos
    row["hour_sin"] = math.sin(2 * math.pi * now.hour / 24)
    row["hour_cos"] = math.cos(2 * math.pi * now.hour / 24)

    # Month sin/cos
    row["month_sin"] = math.sin(2 * math.pi * now.month / 12)
    row["month_cos"] = math.cos(2 * math.pi * now.month / 12)

    # Neighbor features — use NOAA data or fallback to LRIA values
    for station in NEIGHBOR_STATIONS:
        prefix = station.lower()
        nb = neighbors.get(station, {})

        # Use neighbor data if available, otherwise fallback to LRIA
        nb_temp   = nb.get("temperature_c", req.temperature_c)
        nb_dewp   = nb.get("dewpoint_c", req.dewpoint_c)
        nb_vis    = nb.get("visibility_m", float(req.visibility_m))
        nb_wspd   = nb.get("wind_speed_mps", float(req.wind_speed_mps))
        nb_wdir   = nb.get("wind_dir_deg", float(req.wind_dir_deg))
        nb_hum    = nb.get("humidity_pct", row["humidity_magnus"])

        row[f"{prefix}_visibility_m"]   = nb_vis
        row[f"{prefix}_temperature_c"]  = nb_temp
        row[f"{prefix}_dewpoint_c"]     = nb_dewp
        row[f"{prefix}_wind_speed_mps"] = nb_wspd
        row[f"{prefix}_humidity_pct"]   = nb_hum

        nb_wd_rad = math.radians(nb_wdir)
        row[f"{prefix}_wind_dir_sin"] = math.sin(nb_wd_rad)
        row[f"{prefix}_wind_dir_cos"] = math.cos(nb_wd_rad)

    # Build DataFrame with exactly the feature columns from training
    df = pd.DataFrame([row])

    # Add any missing columns as NaN
    for col in feature_cols:
        if col not in df.columns:
            df[col] = np.nan

    # Reorder to match training
    df = df[feature_cols]

    return df


# ---------------------------------------------------------
# Inference
# ---------------------------------------------------------

def _get_tree_predictions(ensemble, X: pd.DataFrame) -> np.ndarray:
    X_arr = X.values
    return np.column_stack([
        est.predict_proba(X_arr[:, features])[:, 1]
        for est, features in zip(ensemble.estimators_, ensemble.estimators_features_)
    ])


def _predict(X: pd.DataFrame) -> tuple[float, float, float]:
    """Run calibrated inference."""
    ensemble      = _cache["ensemble"]
    calibrator    = _cache["calibrator"]
    calibrator_lo = _cache["calibrator_lo"]
    calibrator_hi = _cache["calibrator_hi"]

    tree_preds = _get_tree_predictions(ensemble, X)

    raw_mean = tree_preds.mean(axis=1)
    raw_p10  = np.percentile(tree_preds, 10, axis=1)
    raw_p90  = np.percentile(tree_preds, 90, axis=1)

    prob    = float(calibrator.predict(raw_mean)[0])
    prob_lo = float(calibrator_lo.predict(raw_p10)[0])
    prob_hi = float(calibrator_hi.predict(raw_p90)[0])

    # Ensure ordering
    prob_lo = min(prob_lo, prob)
    prob_hi = max(prob_hi, prob)

    return prob, prob_lo, prob_hi


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------

INPUT_PATH = Path("data/input.json")


def _supabase_headers() -> dict:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _get_subscribers(flight_number: str) -> list[str]:
    resp = requests.get(
        f"{_SUPABASE_URL}/rest/v1/passenger_notifications",
        headers=_supabase_headers(),
        params={"flight_number": f"eq.{flight_number}", "notified": "eq.false", "select": "email"},
        timeout=10,
    )
    resp.raise_for_status()
    return [row["email"] for row in resp.json()]


def _mark_notified(flight_number: str) -> None:
    requests.patch(
        f"{_SUPABASE_URL}/rest/v1/passenger_notifications",
        headers=_supabase_headers(),
        params={"flight_number": f"eq.{flight_number}"},
        json={"notified": True},
        timeout=10,
    ).raise_for_status()


def _send_email(to: str, flight_code: str, prob: float, alert: str) -> bool:
    pct = round(prob * 100)
    html = f"""
    <div style="font-family:system-ui,sans-serif;max-width:520px;margin:auto">
      <h2>&#9888;&#65039; Risc de ceata — zborul {flight_code}</h2>
      <p>Probabilitate de ceata: <b>{pct}%</b> (nivel: <b>{alert}</b>).</p>
      <p>Va rugam verificati alternativele disponibile in aplicatie.</p>
      <p style="color:#666;font-size:12px">
        Primesti acest email pentru ca te-ai abonat la alertele zborului {flight_code}.
      </p>
    </div>"""
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {_RESEND_KEY}", "Content-Type": "application/json"},
        json={
            "from": _EMAIL_FROM,
            "to": [to],
            "subject": f"Risc de ceata — zborul {flight_code}",
            "html": html,
        },
        timeout=15,
    )
    return resp.ok


class RunResponse(BaseModel):
    prediction: PredictResponse
    emails_sent: int
    emails_total: int


@app.get("/run", response_model=RunResponse)
def run():
    """Citeste data/input.json, ruleaza modelul, trimite email daca alert != silent."""
    if not INPUT_PATH.exists():
        raise HTTPException(status_code=404, detail="data/input.json not found")

    with open(INPUT_PATH) as f:
        body = json.load(f)

    req = PredictRequest(**body)
    _load_artifacts()
    meta = _cache["meta"]

    neighbors = _fetch_noaa_neighbors()
    X = _build_feature_row(req, neighbors)
    prob, prob_lo, prob_hi = _predict(X)

    thr_full  = meta["threshold_full_risk"]
    thr_early = meta["threshold_early_warning"]
    if prob >= thr_full:
        alert = "full_risk"
    elif prob >= thr_early:
        alert = "early_warning"
    else:
        alert = "silent"

    prediction = PredictResponse(
        horizon     = req.horizon,
        observed_at = datetime.now(tz=timezone.utc).isoformat(),
        prob        = round(prob, 4),
        prob_lo     = round(prob_lo, 4),
        prob_hi     = round(prob_hi, 4),
        alert       = alert,
        flight_code = req.flight_code,
    )

    sent = 0
    total = 0
    if alert != "silent" and req.flight_code and _SUPABASE_KEY and _RESEND_KEY:
        try:
            subscribers = _get_subscribers(req.flight_code)
            total = len(subscribers)
            for email in subscribers:
                if _send_email(email, req.flight_code, prob, alert):
                    sent += 1
            if sent > 0:
                _mark_notified(req.flight_code)
        except Exception as e:
            logger.warning("Email dispatch failed: %s", e)

    return RunResponse(prediction=prediction, emails_sent=sent, emails_total=total)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict_fog", response_model=PredictResponse)
def predict_fog(req: PredictRequest):
    _load_artifacts()
    meta = _cache["meta"]

    # Fetch live neighbor data from NOAA
    neighbors = _fetch_noaa_neighbors()

    # Build feature row
    X = _build_feature_row(req, neighbors)

    # Inference
    prob, prob_lo, prob_hi = _predict(X)

    # Alert classification using saved thresholds (three-tier)
    thr_full  = meta["threshold_full_risk"]
    thr_early = meta["threshold_early_warning"]

    if prob >= thr_full:
        alert = "full_risk"
    elif prob >= thr_early:
        alert = "early_warning"
    else:
        alert = "silent"

    return PredictResponse(
        horizon      = req.horizon,
        observed_at  = datetime.now(tz=timezone.utc).isoformat(),
        prob         = round(prob, 4),
        prob_lo      = round(prob_lo, 4),
        prob_hi      = round(prob_hi, 4),
        alert        = alert,
        flight_code  = req.flight_code,
    )


# ---------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
