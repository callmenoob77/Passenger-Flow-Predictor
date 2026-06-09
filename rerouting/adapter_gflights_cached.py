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

USD_TO_EUR = 0.92  # cache prices are scraped in USD; convert so all adapters return EUR

# Reachability (same rules as adapter_nearby_flights):
REACT_H          = 1.0  # passenger needs time to react after the alert
CHECKIN_BUFFER_H = 1.5  # check-in cutoff at the alternative airport
# A flight from the SAME fogged-in airport is only a credible alternative once
# the fog has had time to clear; skip departures inside this window.
SAME_AIRPORT_COOLDOWN_H = 6.0


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

        ground_h = float(r.get("ground_h") or 0.0)
        same_airport = r.get("from_city", "").lower() == flight.origin_city.lower()
        if same_airport:
            # same airport is fogged in — only offer departures after a clearing window
            if dep < flight.scheduled_departure + timedelta(hours=SAME_AIRPORT_COOLDOWN_H):
                continue
        else:
            # must be physically reachable: react + ground transfer + check-in
            if dep < flight.scheduled_departure + timedelta(hours=REACT_H + ground_h + CHECKIN_BUFFER_H):
                continue

        k = (r.get("provider"), r.get("from_iata"), r.get("dep_str"), r.get("price_usd"))
        if k in seen:
            continue
        seen.add(k)
        transfers = 0 if same_airport else 1
        provider = r.get("provider","?")
        if transfers:
            provider = f"{provider} (from {r.get('from_city')})"
        raw = {"ground_h": ground_h, "stops": r.get("stops"),
               "price_usd": price, "cached_date": r.get("date")}
        if same_airport:
            raw["note"] = "departs from the disrupted airport — verify fog has cleared"
        out.append(Option(
            mode="flight", provider=provider,
            depart=dep, arrive=arr, duration_h=dur,
            price_eur=round(price * USD_TO_EUR, 2),
            transfers=transfers, deep_link="https://www.google.com/travel/flights",
            raw=raw,
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
            print(f"  {o.provider:26} {o.depart:%H:%M}->{o.arrive:%H:%M} | {o.duration_h}h | EUR {o.price_eur} | t={o.transfers}")