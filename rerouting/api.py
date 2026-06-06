"""
HTTP API over the resolver.
Run: uvicorn api:app --reload --port 8000
"""

from datetime import datetime, timedelta
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from resolver import Flight, resolve, score
from adapter_flixbus import flixbus_adapter
from adapter_train import train_adapter
from adapter_gflights_cached import gflights_cached_adapter

ADAPTERS = [flixbus_adapter, train_adapter, gflights_cached_adapter]

FLIGHT_DB = {
    # Original Demo Flights
    "RO 6769": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP"},
    "RO 6771": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Londra", "dest_icao": "LTN"},
    "RO 6773": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Roma", "dest_icao": "FCO"},
    "W6 1234": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bergamo", "dest_icao": "BGY"},
    "W6 2345": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP"},
    "FR 4321": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Londra", "dest_icao": "LTN"},
    "RO 707":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP"},

    # Real Flights from Iasi Airport (Departures)
    "A2 131":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP"},
    "A2 137":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP"},
    "OS 704":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Vienna", "dest_icao": "VIE"},
    "OS 706":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Vienna", "dest_icao": "VIE"},
    "H4 7551": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Hurghada", "dest_icao": "HRG"},
    "FR 3113": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bergamo", "dest_icao": "BGY"},
    "FR 3115": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Paris", "dest_icao": "BVA"},
    "RO 708":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP"},
    "W4 3667": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bologna", "dest_icao": "BLQ"},
    "W4 3639": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Basel", "dest_icao": "BSL"},
    "W4 3675": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Roma", "dest_icao": "FCO"},
    "W4 3697": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Liverpool", "dest_icao": "LPL"},
    "W4 3691": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Madrid", "dest_icao": "MAD"},
    "W4 3701": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP"},
    "W4 3669": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Venetia", "dest_icao": "TSF"},
}

def _normalize_key(s: str) -> str:
    return s.upper().replace("-", "").replace(" ", "").strip()

def _find_flight(flight_number: str):
    query = _normalize_key(flight_number)
    for k, v in FLIGHT_DB.items():
        if _normalize_key(k) == query:
            return k, v
    return None, None

CONN = "postgresql://postgres.tuqhlwpmhkirtvgihdxs:AdiDamianGebz@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

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
    return {**route, "flightNumber": key, "scheduled_departure": tomorrow.isoformat()}


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
