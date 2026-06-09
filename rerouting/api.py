"""
HTTP API over the resolver.
Run: uvicorn api:app --reload --port 8000
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import os
import requests as _requests
try:
    import psycopg2
    _HAS_PSYCOPG2 = True
except ImportError:
    _HAS_PSYCOPG2 = False
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from resolver import Flight, resolve, score
from adapter_flixbus import flixbus_adapter
from adapter_train import train_adapter
from adapter_gflights_cached import gflights_cached_adapter
from adapter_nearby_flights import nearby_flights_adapter

ADAPTERS = [flixbus_adapter, train_adapter, gflights_cached_adapter, nearby_flights_adapter]

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import CONN
from flights_db import _find_flight
from flights_board import lookup_board
from flights_live import lookup_flight
import notifier


def _resolve_flight(flight_number: str):
    """Resolve a flight, best source first. Returns (key, route) or (None, None).

    1. LRIA departures board (airport's own API — free, no key, no quota)
    2. AviationStack (any flight worldwide; needs AVIATIONSTACK_API_KEY)
    3. Hardcoded demo FLIGHT_DB (always available, fully offline)
    """
    key, route = lookup_board(flight_number)
    if route:
        return key, route
    key, route = lookup_flight(flight_number)
    if route:
        return key, route
    return _find_flight(flight_number)


_FLIGHT_404 = (
    "Flight not found. Any real Iași departure works (live airport board); "
    "demo flights: RO 6769, OS 704, FR 3113"
)


def _ml_fog_alert(flight_code: str) -> str | None:
    """Ask the ML service for the current fog alert. None if unavailable.
    An empty ML_API_URL disables the call entirely (demo mode)."""
    ml_url = os.environ.get("ML_API_URL", "http://localhost:8001").rstrip("/")
    if not ml_url:
        return None
    try:
        metar = _fetch_current_metar_lria()
        if not metar:
            return None
        ml_res = _requests.post(
            f"{ml_url}/predict_fog",
            json={**metar, "flight_code": flight_code},
            timeout=3,
        )
        if ml_res.status_code == 200:
            return ml_res.json().get("alert")
    except Exception:
        pass  # ML API not running
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # departure-aware email alerts (needs SUPABASE_CONN_STRING + RESEND_API_KEY)
    task = None
    if notifier.enabled(CONN):
        task = asyncio.create_task(notifier.loop(CONN, _resolve_flight, _ml_fog_alert))
    yield
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Fog Copilot - Rerouting", lifespan=lifespan)

_allowed_origins = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
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
    key, route = _resolve_flight(flight_number)
    if not route:
        raise HTTPException(status_code=404, detail=_FLIGHT_404)

    # Real schedule when the live API provided one; demo placeholder otherwise.
    scheduled = route.get("scheduled_departure")
    if not scheduled:
        scheduled = (datetime.now() + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        ).isoformat()

    # Overlay the live ML fog prediction. The fog signal can only escalate a
    # flight to FOG_RISK — it never clears an airline-reported CANCELLED/DELAYED.
    status = route.get("status", "ON_TIME")
    if status not in ("CANCELLED",):
        alert = _ml_fog_alert(key)
        if alert in ("full_risk", "early_warning"):
            status = "FOG_RISK"

    return {**route, "flightNumber": key, "scheduled_departure": scheduled, "status": status}


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
    # Adapters work with naive local datetimes; a tz-aware departure (e.g. from
    # the live flight API) would make the comparisons in resolve() raise.
    departure = body.scheduled_departure.replace(tzinfo=None)
    f = Flight(body.origin_city, body.origin_icao, body.dest_city,
               body.dest_icao, departure)
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


@app.api_route("/notify/run", methods=["GET", "POST"])
def notify_run():
    """Run one notifier pass on demand (GitHub Actions calls this every 15 min
    in production). The in-process loop does the same thing continuously, but
    on free-tier hosting the service sleeps between requests and loops stop —
    this endpoint both wakes the service and performs the check."""
    if not notifier.enabled(CONN):
        return {"enabled": False, "detail": "Set SUPABASE_CONN_STRING + RESEND_API_KEY to activate notifications"}
    result = notifier.check_once(CONN, _resolve_flight, _ml_fog_alert)
    return {"enabled": True, **result}


@app.post("/subscribe")
def subscribe(body: SubscribeIn):
    # Validate flight number (live API or demo database)
    key, route = _resolve_flight(body.flight_number)
    if not route:
        raise HTTPException(status_code=404, detail=_FLIGHT_404)

    if CONN and _HAS_PSYCOPG2:
        conn = None
        try:
            conn = psycopg2.connect(CONN)
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO passenger_notifications (email, flight_number)
                    VALUES (%s, %s)
                    ON CONFLICT (email, flight_number) DO NOTHING
                    """,
                    (body.email.strip().lower(), key)
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        finally:
            if conn is not None:
                conn.close()

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

    # Normalize flight number (live API or demo database)
    key, route = _resolve_flight(body.flight_number)
    if not route:
        raise HTTPException(status_code=404, detail=_FLIGHT_404)

    if CONN and _HAS_PSYCOPG2:
        conn = None
        try:
            conn = psycopg2.connect(CONN)
            with conn, conn.cursor() as cur:
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
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        finally:
            if conn is not None:
                conn.close()

    return {"ok": True, "message": f"Refund request successfully submitted for {body.full_name} under PNR {pnr}"}

# Trigger Uvicorn cache reload

