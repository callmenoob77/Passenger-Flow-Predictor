"""
HTTP API over the resolver.
Run: uvicorn api:app --reload --port 8000
"""

from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from resolver import Flight, resolve, score
from adapter_flixbus import flixbus_adapter
from adapter_train import train_adapter
from adapter_gflights_cached import gflights_cached_adapter

ADAPTERS = [flixbus_adapter, train_adapter, gflights_cached_adapter]

FLIGHT_DB = {
    "RO 6769": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP"},
    "RO 6771": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Londra", "dest_icao": "LTN"},
    "RO 6773": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Roma", "dest_icao": "FCO"},
    "W6 1234": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bergamo", "dest_icao": "BGY"},
    "W6 2345": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP"},
    "FR 4321": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Londra", "dest_icao": "LTN"},
}

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
    key = flight_number.upper().replace("-", " ").strip()
    if key not in FLIGHT_DB:
        raise HTTPException(status_code=404, detail=f"Flight not found in demo database. Try: RO 6769, W6 2345, FR 4321")
    route = FLIGHT_DB[key]
    tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    return {**route, "scheduled_departure": tomorrow.isoformat()}


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
