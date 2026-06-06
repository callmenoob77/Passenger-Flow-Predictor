"""
GOOGLE FLIGHTS Adapter (from CACHE, date-based) — reads gflights_cache.json.
Does NOT hit Google -> won't break during demo. Cache has 7 days of real data.

Refresh: run capture_gflights.py from an environment where the scraper works.
"""

import json, os
from datetime import datetime, timedelta
from resolver import Flight, Option

_CACHE_PATH = os.path.join(os.path.dirname(__file__), "gflights_cache.json")
try:
    _CACHE = json.load(open(_CACHE_PATH, encoding="utf-8"))
except Exception:
    _CACHE = {}


def _price(s):
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def _dur_h(s):
    if not s: return None
    p = str(s).split(); h = m = 0
    for i, x in enumerate(p):
        if x == "hr" and i: h = int(p[i-1])
        if x == "min" and i: m = int(p[i-1])
    return round(h + m/60, 1) if (h or m) else None


def _time_of(s):
    # "10:00 PM on Sat, Jun 20" -> time
    try:
        return datetime.strptime(s.split(" on ")[0].strip(), "%I:%M %p").time()
    except Exception:
        return None


def gflights_cached_adapter(flight: Flight) -> list:
    qdate = flight.scheduled_departure.date()
    rows = []
    for key, lst in _CACHE.items():
        if key.split("|")[0] == flight.dest_city.lower():
            rows.extend(lst)
    if not rows:
        return []

    # 1) prefer rows from EXACTLY the requested date; otherwise fall back to any day (rebased)
    exact = [r for r in rows if r.get("date") == qdate.isoformat()]
    use = exact if exact else rows

    out, seen = [], set()
    for r in use:
        t = _time_of(r.get("dep_str", ""))
        dur = _dur_h(r.get("duration"))
        price = _price(r.get("price_usd"))
        if t is None or dur is None or price is None:
            continue
        dep = datetime.combine(qdate, t)          # always on the requested date
        arr = dep + timedelta(hours=dur)          # arrival = departure + duration
        if dep <= flight.scheduled_departure:
            continue  # only flights departing AFTER the cancelled flight
        k = (r.get("provider"), r.get("from_iata"), r.get("dep_str"), r.get("price_usd"))
        if k in seen:
            continue
        seen.add(k)
        transfers = 0 if r.get("from_city","").lower() == flight.origin_city.lower() else 1
        provider = r.get("provider","?")
        if transfers:
            provider = f"{provider} (from {r.get('from_city')})"
        out.append(Option(
            mode="flight", provider=provider,
            depart=dep, arrive=arr, duration_h=dur, price_eur=price,  # USD
            transfers=transfers, deep_link="https://www.google.com/travel/flights",
            raw={"ground_h": r.get("ground_h"), "stops": r.get("stops"),
                 "currency": "USD", "cached_date": r.get("date")},
        ))
    out.sort(key=lambda o: (o.arrive or datetime.max, o.price_eur or 9999))
    return out


if __name__ == "__main__":
    days = sorted({r["date"] for v in _CACHE.values() for r in v})
    print("Days in cache:", days[0], "->", days[-1] if days else "—")
    for dest in ["Milano", "Roma", "Barcelona"]:
        f = Flight("Iasi", "IAS", dest, "", datetime.strptime(days[2], "%Y-%m-%d").replace(hour=7))
        print(f"\n=== {dest}, {f.scheduled_departure.date()} ===")
        for o in gflights_cached_adapter(f)[:4]:
            print(f"  {o.provider:26} {o.depart:%H:%M}->{o.arrive:%H:%M} | {o.duration_h}h | ${o.price_eur} | t={o.transfers}")