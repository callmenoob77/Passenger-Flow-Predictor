"""
Live LRIA departures board — the Iași airport's own public flights API
(the same backend the website's departures page polls every 60 s).
Free, no API key, no quota. Primary source for flight lookups.

Status codes (from the /status endpoint):
    0 Scheduled · 1 Departed · 2 Landed · 3 Delayed · 4 Canceled
    5 Check-in · 6 Boarding

Field semantics quirk: rows display the local departure time in the `time`
string ("HH:MM"), with the service day given by the `date` bucket (21:00 UTC
of the previous day = local midnight). The departAt/arriveAt fields do NOT
reliably hold what their names suggest, so they are only used as fallbacks.

TLS note: the server presents a valid Let's Encrypt certificate but omits the
intermediate CA from its chain. Browsers repair this silently; Python does not.
Requests are therefore verified against certifi's roots PLUS the official
Let's Encrypt intermediates shipped in letsencrypt_intermediates.pem —
certificate verification stays ON.
"""

import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import certifi
import requests

from flights_live import _normalize, _pretty_key

BASE_URL = os.environ.get("LRIA_BOARD_URL", "https://www.aeroport-iasi.ro:5000").rstrip("/")

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Bucharest")
except Exception:  # missing tz database — close enough for a departures board
    LOCAL_TZ = timezone(timedelta(hours=3))

_CACHE_TTL_OK   = 120   # board refreshes every 60 s; 2 min staleness is fine
_CACHE_TTL_FAIL = 60
_cache: dict[str, tuple[float, dict | None]] = {}

_INTERMEDIATES = Path(__file__).parent / "letsencrypt_intermediates.pem"
_bundle_path: str | None = None


def _ca_bundle() -> str:
    """certifi roots + Let's Encrypt intermediates, combined once per process."""
    global _bundle_path
    if _bundle_path is None:
        combined = Path(tempfile.gettempdir()) / "hecatron_ca_bundle.pem"
        combined.write_bytes(
            Path(certifi.where()).read_bytes() + b"\n" + _INTERMEDIATES.read_bytes()
        )
        _bundle_path = str(combined)
    return _bundle_path


# Romanian board names -> city names used by FLIGHT_DB, the transport
# adapters and the gflights cache keys (milano, roma, londra, vienna...)
CITY_MAP = {
    "BUCURESTI": "Bucharest", "VIENA": "Vienna", "BRUXELLES": "Brussels",
    "MILANO": "Milano", "BERGAMO": "Bergamo", "ROMA": "Roma", "LONDRA": "Londra",
    "VENETIA": "Venetia", "PARIS": "Paris", "MUNCHEN": "Munich",
}

# Fallback IATA codes for destinations the board lists without one
CITY_IATA = {
    "Bucharest": "OTP", "Vienna": "VIE", "Brussels": "CRL", "Milano": "MXP",
    "Bergamo": "BGY", "Roma": "FCO", "Londra": "LTN", "Venetia": "TSF",
    "Paris": "BVA", "Barcelona": "BCN", "Dublin": "DUB", "Bologna": "BLQ",
    "Basel": "BSL", "Liverpool": "LPL", "Madrid": "MAD", "Hurghada": "HRG",
}

STATUS_MAP = {
    0: "ON_TIME",    # Scheduled
    1: "ON_TIME",    # Departed
    2: "ON_TIME",    # Landed
    3: "DELAYED",
    4: "CANCELLED",
    5: "ON_TIME",    # Check-in
    6: "ON_TIME",    # Boarding
}


def _parse_dest(s: str) -> tuple[str, str]:
    """'BUCURESTI (OTP)' -> ('Bucharest', 'OTP'); 'BERGAMO' -> ('Bergamo', 'BGY')."""
    s = (s or "").strip()
    iata = ""
    if s.endswith(")") and "(" in s:
        s, _, tail = s.rpartition("(")
        iata = tail.rstrip(")").strip()
        s = s.strip()
    city = CITY_MAP.get(s.upper(), s.title())
    return city, iata or CITY_IATA.get(city, "")


def _scheduled_local(row: dict) -> datetime | None:
    """Local scheduled departure: service day from the `date` bucket + `time` HH:MM."""
    bucket = row.get("date") or row.get("intervalStart")
    if not bucket:
        return None
    try:
        day = (
            datetime.fromisoformat(bucket.replace("Z", "+00:00"))
            .astimezone(LOCAL_TZ)
            .date()
        )
    except ValueError:
        return None

    hhmm = (row.get("time") or "").strip()
    if hhmm:
        try:
            h, m = map(int, hhmm.split(":"))
            return datetime(day.year, day.month, day.day, h, m)
        except ValueError:
            pass

    # fallback: arriveAt (which in practice holds the displayed local time as UTC)
    for field in ("arriveAt", "departAt"):
        v = row.get(field)
        if v:
            try:
                return (
                    datetime.fromisoformat(v.replace("Z", "+00:00"))
                    .astimezone(LOCAL_TZ)
                    .replace(tzinfo=None)
                )
            except ValueError:
                continue
    return None


def _map_row(row: dict) -> dict:
    dest_city, dest_iata = _parse_dest(row.get("to", ""))
    if row.get("canceled") or row.get("status") == 4:
        status = "CANCELLED"
    else:
        status = STATUS_MAP.get(row.get("status"), "ON_TIME")
    sched = _scheduled_local(row)
    return {
        "origin_city": "Iasi",
        "origin_icao": "LRIA",
        "dest_city":   dest_city,
        "dest_icao":   dest_iata,
        "status":      status,
        "scheduled_departure": sched.isoformat() if sched else None,
        "airline":     (row.get("company") or {}).get("name"),
        "source":      "lria-board",
    }


def lookup_board(flight_number: str) -> tuple[str | None, dict | None]:
    """Look up a departure on the live LRIA board. Returns (key, route) or (None, None).

    Never raises — any problem (server down, TLS, schema change) yields
    (None, None) so callers can fall back to other sources.
    """
    if not BASE_URL:
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
            f"{BASE_URL}/flight",
            params={"where": json.dumps({"code": code, "from": "IASI"}), "limit": 60},
            timeout=8,
            verify=_ca_bundle(),
            headers={"User-Agent": "Mozilla/5.0 (FogCopilot)"},
        )
        resp.raise_for_status()
        rows = resp.json()
        if isinstance(rows, list) and rows:
            local_now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
            dated = [(r, _scheduled_local(r)) for r in rows]
            dated = [(r, s) for r, s in dated if s is not None]
            # earliest upcoming departure (with a 2h grace for just-departed ones)
            upcoming = sorted(
                (item for item in dated if item[1] >= local_now - timedelta(hours=2)),
                key=lambda item: item[1],
            )
            if upcoming:
                route = _map_row(upcoming[0][0])
            else:
                # flight exists but only in the past 24h -> still report it
                recent = max(dated, key=lambda item: item[1], default=None)
                if recent and recent[1] >= local_now - timedelta(hours=24):
                    route = _map_row(recent[0])
    except Exception as exc:
        print(f"[flights_board] lookup failed for {code}: {exc}")

    _cache[code] = (now + (_CACHE_TTL_OK if route else _CACHE_TTL_FAIL), route)
    return (_pretty_key(code), route) if route else (None, None)


if __name__ == "__main__":
    import sys

    flights = sys.argv[1:] or ["OS 704", "FR3113", "A2 131", "XX 9999"]
    for fn in flights:
        key, route = lookup_board(fn)
        if route:
            print(f"{fn!r} -> {key}: {route['dest_city']} ({route['dest_icao']}) "
                  f"{route['status']} dep {route['scheduled_departure']} [{route['airline']}]")
        else:
            print(f"{fn!r} -> not on the LRIA board")
