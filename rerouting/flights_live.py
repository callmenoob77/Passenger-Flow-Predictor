"""
Live flight lookup via AviationStack (https://aviationstack.com).

Optional: set AVIATIONSTACK_API_KEY in the root .env (free key from
https://aviationstack.com/signup/free). Without a key, lookup_flight()
returns (None, None) and the API falls back to the demo FLIGHT_DB.

Free-tier notes:
  - free keys only work over plain HTTP (https is a paid feature),
    hence the http:// base URL below
  - quota is ~100 requests/month -> responses are cached in-memory
"""

import os
import re
import time
from datetime import datetime

import requests

BASE_URL = os.environ.get("AVIATIONSTACK_BASE_URL", "http://api.aviationstack.com/v1")

_CACHE_TTL_OK   = 600   # seconds to reuse a successful lookup
_CACHE_TTL_FAIL = 120   # seconds before retrying a failed lookup
_cache: dict[str, tuple[float, dict | None]] = {}  # "RO6769" -> (expires_at, route|None)

_DEP_TTL_OK   = 6 * 3600  # airport departure boards change rarely; 6h keeps quota tiny
_DEP_TTL_FAIL = 600
_dep_cache: dict[str, tuple[float, list]] = {}  # "SCV" -> (expires_at, entries)

# IATA -> city names matching the conventions used by FLIGHT_DB, the
# FlixBus/train adapters and the gflights cache keys (milano, roma, londra...).
IATA_CITY = {
    "IAS": "Iasi",
    "OTP": "Bucharest", "BBU": "Bucharest",
    "MXP": "Milano", "LIN": "Milano",
    "BGY": "Bergamo",
    "LTN": "Londra", "STN": "Londra", "LGW": "Londra", "LHR": "Londra",
    "FCO": "Roma", "CIA": "Roma",
    "VIE": "Vienna",
    "BCN": "Barcelona",
    "DUB": "Dublin",
    "BLQ": "Bologna",
    "BSL": "Basel",
    "LPL": "Liverpool",
    "MAD": "Madrid",
    "TSF": "Venetia", "VCE": "Venetia",
    "BVA": "Paris", "CDG": "Paris", "ORY": "Paris",
    "CRL": "Brussels", "BRU": "Brussels",
    "HRG": "Hurghada",
    "SCV": "Suceava", "BCM": "Bacau", "KIV": "Chisinau",
}


def _normalize(flight_number: str) -> str:
    """'ro 6769' / 'RO-6769' -> 'RO6769' (AviationStack flight_iata format)."""
    return re.sub(r"[\s\-]", "", flight_number.upper().strip())


def _pretty_key(code: str) -> str:
    """'RO6769' -> 'RO 6769' (display format used across the app)."""
    m = re.match(r"^([A-Z][A-Z0-9])(\d+)$", code)
    return f"{m.group(1)} {m.group(2)}" if m else code


def _clean_airport_name(name: str) -> str:
    """'Milano Malpensa International Airport' -> 'Milano Malpensa'."""
    for word in ("International", "Intl", "Airport"):
        name = name.replace(word, "")
    return " ".join(name.split())


def _city(airport: dict) -> str:
    iata = (airport.get("iata") or "").upper()
    if iata in IATA_CITY:
        return IATA_CITY[iata]
    return _clean_airport_name(airport.get("airport") or "") or iata


def _naive_iso(s: str | None) -> str | None:
    """AviationStack reports airport-local times with a (bogus) +00:00 offset;
    strip the offset and keep them as naive local timestamps like the adapters."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None).isoformat()
    except ValueError:
        return None


def _pick_entry(entries: list) -> dict | None:
    """Prefer the most recent flight_date, and upcoming/in-flight legs over landed ones."""
    if not entries:
        return None
    entries = sorted(entries, key=lambda e: e.get("flight_date") or "", reverse=True)
    for e in entries:
        if e.get("flight_status") in ("scheduled", "active", "delayed"):
            return e
    return entries[0]


def _map_entry(entry: dict) -> dict:
    """AviationStack response entry -> route dict in FLIGHT_DB shape."""
    dep = entry.get("departure") or {}
    arr = entry.get("arrival") or {}

    flight_status = entry.get("flight_status")
    delay_min = dep.get("delay")
    if flight_status in ("cancelled", "incident"):
        status = "CANCELLED"
    elif delay_min and float(delay_min) >= 45:
        status = "DELAYED"
    else:
        status = "ON_TIME"

    return {
        "origin_city": _city(dep),
        "origin_icao": dep.get("icao") or dep.get("iata") or "",
        "dest_city":   _city(arr),
        # FLIGHT_DB stores the 3-letter IATA code here (MXP, OTP...) — keep that shape
        "dest_icao":   arr.get("iata") or arr.get("icao") or "",
        "status":      status,
        "scheduled_departure": _naive_iso(dep.get("scheduled")),
        "airline":     (entry.get("airline") or {}).get("name"),
        "source":      "aviationstack",
    }


def lookup_flight(flight_number: str) -> tuple[str | None, dict | None]:
    """Look up a real flight. Returns (key, route) or (None, None).

    Never raises — any API problem (no key, quota, network, bad payload)
    results in (None, None) so callers can fall back to the demo DB.
    """
    api_key = os.environ.get("AVIATIONSTACK_API_KEY")
    if not api_key:
        return None, None

    code = _normalize(flight_number)
    now = time.time()
    hit = _cache.get(code)
    if hit and hit[0] > now:
        route = hit[1]
        return (_pretty_key(code), route) if route else (None, None)

    route = None
    try:
        resp = requests.get(
            f"{BASE_URL}/flights",
            params={"access_key": api_key, "flight_iata": code, "limit": 10},
            timeout=8,
        )
        resp.raise_for_status()
        payload = resp.json()
        entry = _pick_entry(payload.get("data") or [])
        if entry:
            route = _map_entry(entry)
    except Exception as exc:
        print(f"[flights_live] lookup failed for {code}: {exc}")

    _cache[code] = (now + (_CACHE_TTL_OK if route else _CACHE_TTL_FAIL), route)
    return (_pretty_key(code), route) if route else (None, None)


def departures(dep_iata: str) -> list[dict]:
    """Today's scheduled departures from an airport (raw AviationStack entries).

    One request per airport per 6h thanks to caching, so the free quota lasts.
    Returns [] without a key or on any failure — never raises.
    """
    api_key = os.environ.get("AVIATIONSTACK_API_KEY")
    if not api_key:
        return []

    dep_iata = dep_iata.upper()
    now = time.time()
    hit = _dep_cache.get(dep_iata)
    if hit and hit[0] > now:
        return hit[1]

    rows: list = []
    try:
        resp = requests.get(
            f"{BASE_URL}/flights",
            params={"access_key": api_key, "dep_iata": dep_iata, "limit": 100},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json().get("data") or []
    except Exception as exc:
        print(f"[flights_live] departures({dep_iata}) failed: {exc}")

    _dep_cache[dep_iata] = (now + (_DEP_TTL_OK if rows else _DEP_TTL_FAIL), rows)
    return rows


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    # offline self-test of the response mapping
    sample = {
        "flight_date": "2026-06-10",
        "flight_status": "scheduled",
        "departure": {"airport": "Iasi International Airport", "iata": "IAS", "icao": "LRIA",
                      "scheduled": "2026-06-10T08:25:00+00:00", "delay": None},
        "arrival": {"airport": "Malpensa International Airport", "iata": "MXP", "icao": "LIMC",
                    "scheduled": "2026-06-10T09:55:00+00:00"},
        "airline": {"name": "Tarom", "iata": "RO"},
        "flight": {"number": "6769", "iata": "RO6769"},
    }
    print("offline mapping test:")
    print(json.dumps(_map_entry(sample), indent=2))
    assert _pretty_key(_normalize("ro-6769")) == "RO 6769"

    # live test if a key is configured and a flight number is passed
    if len(sys.argv) > 1:
        sys.path.append(str(Path(__file__).parent.parent))
        import config  # noqa: F401  (loads root .env)
        key, route = lookup_flight(sys.argv[1])
        print(f"\nlive lookup {sys.argv[1]!r} -> key={key}")
        print(json.dumps(route, indent=2) if route else "  no result (no key / quota / unknown flight)")
