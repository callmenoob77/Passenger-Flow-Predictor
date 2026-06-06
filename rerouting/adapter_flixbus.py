"""
FLIXBUS Adapter (option 1, ground transport) — direct FlixBus backend, NO API key.
Public endpoint used by their website; unofficial but functional and no auth required.
Returns real trips with price, times, and transfers.
"""

from datetime import datetime
import requests

from resolver import Flight, Option

AUTOCOMPLETE = "https://global.api.flixbus.com/search/autocomplete/cities"
SEARCH = "https://global.api.flixbus.com/search/service/v4/search"

_city_cache = {}


def _city_id(name: str):
    if name in _city_cache:
        return _city_cache[name]
    r = requests.get(AUTOCOMPLETE, params={"q": name}, timeout=20)
    r.raise_for_status()
    data = r.json()
    cid = data[0]["id"] if data else None
    _city_cache[name] = cid
    return cid


def _iso_naive(s: str):
    """'2026-06-09T09:30:00+03:00' -> naive datetime (local time)."""
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except Exception:
        return None


def flixbus_adapter(flight: Flight) -> list:
    origin = _city_id(flight.origin_city)
    dest = _city_id(flight.dest_city)
    if not origin or not dest:
        print(f"[flixbus] city not found (origin={origin}, dest={dest})")
        return []

    params = {
        "from_city_id": origin, "to_city_id": dest,
        "departure_date": flight.scheduled_departure.strftime("%d.%m.%Y"),
        "products": '{"adult":1}', "currency": "EUR", "locale": "en",
        "search_by": "cities", "include_after_midnight_rides": "1",
    }
    r = requests.get(SEARCH, params=params, timeout=30)
    r.raise_for_status()
    trips = r.json().get("trips", [])
    if not trips:
        return []

    out = []
    for rid, res in trips[0].get("results", {}).items():
        if res.get("status") != "available":
            continue
        depart = _iso_naive(res.get("departure", {}).get("date", ""))
        arrive = _iso_naive(res.get("arrival", {}).get("date", ""))
        if depart is None or depart <= flight.scheduled_departure:
            continue  # only trips departing AFTER the cancelled flight
        dur = round((arrive - depart).total_seconds() / 3600, 1) if arrive else None
        out.append(Option(
            mode="bus", provider="FlixBus",
            depart=depart, arrive=arrive, duration_h=dur,
            price_eur=res.get("price", {}).get("total"),
            transfers=res.get("transfers") or 0,
            deep_link="https://shop.flixbus.com/search",
            raw={"trip_id": rid},
        ))
    return out


if __name__ == "__main__":
    f = Flight("Iasi", "LRIA", "Bucharest", "LROP",
               datetime.now().replace(hour=6, minute=0, second=0, microsecond=0))
    print(f"FlixBus trips {f.origin_city}->{f.dest_city} on {f.scheduled_departure:%d.%m.%Y}, after {f.scheduled_departure:%H:%M}:\n")
    for o in flixbus_adapter(f):
        print(f"  {o.provider} {o.depart:%H:%M}->{o.arrive:%H:%M} | {o.duration_h}h | {o.price_eur} EUR | transfers={o.transfers}")