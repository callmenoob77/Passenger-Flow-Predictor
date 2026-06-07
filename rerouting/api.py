"""
HTTP API over the resolver.
Run: uvicorn api:app --reload --port 8000
"""

from datetime import datetime, timedelta
import os
import requests as _requests
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from resolver import Flight, resolve, score
from adapter_flixbus import flixbus_adapter
from adapter_train import train_adapter
from adapter_gflights_cached import gflights_cached_adapter

ADAPTERS = [flixbus_adapter, train_adapter, gflights_cached_adapter]

import sys
from pathlib import Path
# Add project root to sys.path so we can import config.py
sys.path.append(str(Path(__file__).parent.parent))

from config import CONN
from flights_db import FLIGHT_DB, _find_flight

app = FastAPI(title="Fog Copilot - Rerouting")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class FlightIn(BaseModel):
    origin_city: str
    origin_icao: str = ""
    dest_city: str
    dest_icao: str = ""
    scheduled_departure: datetime


class SubscribeIn(BaseModel):
    email: str
    flight_number: str


class RefundIn(BaseModel):
    flight_number: str
    full_name: str
    email: str
    phone: str
    pnr: str
    refund_type: str
    notes: str = ""


def _opt_to_dict(o, f):
    return {
        "mode": o.mode,
        "provider": o.provider,
        "depart": o.depart.isoformat() if o.depart else None,
        "arrive": o.arrive.isoformat() if o.arrive else None,
        "duration_h": o.duration_h,
        "price_eur": o.price_eur,
        "transfers": o.transfers,
        "deep_link": o.deep_link,
        "score": round(score(o, f), 1),
    }


@app.get("/flight/{flight_number}")
def flight_lookup(flight_number: str):
    key, route = _find_flight(flight_number)
    if not route:
        raise HTTPException(
            status_code=404,
            detail=f"Flight not found in database. Try: RO 6769, OS 704, FR 3113"
        )
    tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)

    # Try live ML prediction; fall back to hardcoded status if ML API not running
    status = route.get("status", "ON_TIME")
    ml_url = os.environ.get("ML_API_URL", "http://localhost:8001")
    try:
        metar = _fetch_current_metar_lria()
        if metar:
            ml_res = _requests.post(
                f"{ml_url}/predict_fog",
                json={**metar, "flight_code": key},
                timeout=3,
            )
            if ml_res.status_code == 200:
                alert = ml_res.json().get("alert", "silent")
                status = "FOG_RISK" if alert in ("full_risk", "early_warning") else "ON_TIME"
    except Exception:
        pass  # ML API not running — use FLIGHT_DB status

    return {**route, "flightNumber": key, "scheduled_departure": tomorrow.isoformat(), "status": status}


def _fetch_current_metar_lria() -> dict | None:
    """Fetch latest METAR for LRIA from NOAA and return feature dict for ML API."""
    try:
        r = _requests.get(
            "https://aviationweather.gov/api/data/metar",
            params={"ids": "LRIA", "format": "json", "hours": 1},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        obs = data[0]
        vis_mi = obs.get("visib")
        temp   = obs.get("temp")
        dewp   = obs.get("dewp")
        wspd   = obs.get("wspd")
        wdir   = obs.get("wdir")
        if any(v is None for v in [vis_mi, temp, dewp, wspd, wdir]):
            return None
        return {
            "visibility_m":   float(vis_mi) * 1609.344,
            "temperature_c":  float(temp),
            "dewpoint_c":     float(dewp),
            "wind_speed_mps": float(wspd) * 0.514444,
            "wind_dir_deg":   int(wdir),
        }
    except Exception:
        return None


@app.post("/reroute")
def reroute(body: FlightIn, top_n: int = 5):
    f = Flight(body.origin_city, body.origin_icao, body.dest_city,
               body.dest_icao, body.scheduled_departure)
    opts = resolve(f, ADAPTERS, top_n=top_n)
    return {
        "cancelled_flight": {
            "origin": f.origin_city, "dest": f.dest_city,
            "scheduled_departure": f.scheduled_departure.isoformat(),
        },
        "options": [_opt_to_dict(o, f) for o in opts],
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/subscribe")
def subscribe(body: SubscribeIn):
    # Validate flight number exists in database
    key, route = _find_flight(body.flight_number)
    if not route:
        raise HTTPException(
            status_code=404,
            detail=f"Flight not found in database. Try: RO 6769, OS 704, FR 3113"
        )

    # Insert subscription to database
    try:
        conn = psycopg2.connect(CONN)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO passenger_notifications (email, flight_number)
            VALUES (%s, %s)
            ON CONFLICT (email, flight_number) DO NOTHING
            """,
            (body.email.strip().lower(), key)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )

    return {"ok": True, "message": f"Successfully subscribed {body.email} to flight {key}"}


@app.post("/refund")
def claim_refund(body: RefundIn):
    # Validate PNR is alphanumeric and 6 characters
    pnr = body.pnr.strip().upper()
    if len(pnr) != 6 or not pnr.isalnum():
        raise HTTPException(
            status_code=400,
            detail="Invalid Booking Reference (PNR). Must be a 6-character alphanumeric code."
        )

    # Normalize flight number
    key, route = _find_flight(body.flight_number)
    if not route:
        raise HTTPException(
            status_code=404,
            detail=f"Flight not found in database. Try: RO 6769, OS 704, FR 3113"
        )

    try:
        conn = psycopg2.connect(CONN)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO refund_requests (flight_number, full_name, email, phone, pnr, refund_type, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                key,
                body.full_name.strip(),
                body.email.strip().lower(),
                body.phone.strip(),
                pnr,
                body.refund_type.strip(),
                body.notes.strip() if body.notes else None
            )
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )

    return {"ok": True, "message": f"Refund request successfully submitted for {body.full_name} under PNR {pnr}"}

# Trigger Uvicorn cache reload

