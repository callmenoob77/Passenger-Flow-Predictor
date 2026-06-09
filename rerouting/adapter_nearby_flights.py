"""
NEARBY-AIRPORTS Adapter — when Iasi is fogged in, flights still leave from
Chisinau (KIV), Suceava (SCV) and Bacau (BCM).

For the cancelled flight's destination, this adapter:
  1. pulls today's departures from each nearby airport (AviationStack,
     needs AVIATIONSTACK_API_KEY; one cached request per airport per 6h),
  2. keeps the flights going to the same destination city,
  3. pairs each flight with a real ground leg from Iasi (FlixBus live +
     CFR static timetable) that arrives >= CHECKIN_BUFFER_H before departure,
  4. returns ONE combined Option per flight: depart = when the bus/train
     leaves Iasi, arrive = when the flight lands at the destination.

Without an API key (or when nothing matches) it returns [] — the cached
Google-Flights adapter still provides offline nearby-airport options.
"""

from datetime import datetime, timedelta

from resolver import Flight, Option
from flights_live import departures, _naive_iso
from adapter_flixbus import flixbus_adapter
from adapter_train import train_adapter

NEARBY_AIRPORTS = [
    {"iata": "BCM", "city": "Bacau",    "ground_h_est": 2.5},
    {"iata": "SCV", "city": "Suceava",  "ground_h_est": 3.0},
    {"iata": "KIV", "city": "Chisinau", "ground_h_est": 4.0},  # incl. border crossing
]

CHECKIN_BUFFER_H = 1.5   # ground leg must arrive this long before the flight
MIN_REACT_H      = 1.0   # passenger needs time to react after the alert

# Destination city -> acceptable arrival airports (a Milano passenger is happy
# to land at MXP, BGY or LIN). Keys match FLIGHT_DB / board city conventions.
CITY_AIRPORTS = {
    "milano":    {"MXP", "BGY", "LIN"},
    "bergamo":   {"BGY", "MXP", "LIN"},
    "londra":    {"LTN", "STN", "LGW", "LHR"},
    "london":    {"LTN", "STN", "LGW", "LHR"},
    "roma":      {"FCO", "CIA"},
    "rome":      {"FCO", "CIA"},
    "paris":     {"BVA", "CDG", "ORY"},
    "venetia":   {"TSF", "VCE"},
    "bucharest": {"OTP", "BBU"},
    "bucuresti": {"OTP", "BBU"},
    "vienna":    {"VIE"},
    "barcelona": {"BCN"},
    "dublin":    {"DUB"},
    "bologna":   {"BLQ"},
    "basel":     {"BSL"},
    "liverpool": {"LPL"},
    "madrid":    {"MAD"},
    "brussels":  {"CRL", "BRU"},
}


def _dest_codes(flight: Flight) -> set[str]:
    codes = set(CITY_AIRPORTS.get(flight.dest_city.lower(), set()))
    if flight.dest_icao:
        codes.add(flight.dest_icao.upper())
    return codes


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _ground_legs(city: str, ref: datetime) -> list[Option]:
    """All bus/train legs Iasi -> city departing after ref. Adapter failures skipped."""
    legs: list[Option] = []
    probe = Flight("Iasi", "LRIA", city, "", ref)
    for adapter in (flixbus_adapter, train_adapter):
        try:
            legs.extend(adapter(probe))
        except Exception:
            pass
    return [leg for leg in legs if leg.depart and leg.arrive]


def nearby_flights_adapter(flight: Flight) -> list:
    dest_codes = _dest_codes(flight)
    if not dest_codes or flight.origin_city.lower() != "iasi":
        return []

    earliest_leave = flight.scheduled_departure + timedelta(hours=MIN_REACT_H)
    out: list[Option] = []

    for airport in NEARBY_AIRPORTS:
        entries = departures(airport["iata"])
        if not entries:
            continue

        legs = None  # fetched lazily, once per airport
        for entry in entries:
            arr = entry.get("arrival") or {}
            if (arr.get("iata") or "").upper() not in dest_codes:
                continue
            if entry.get("flight_status") in ("cancelled", "incident", "landed"):
                continue

            dep_dt = _parse_dt(_naive_iso((entry.get("departure") or {}).get("scheduled")))
            arr_dt = _parse_dt(_naive_iso(arr.get("scheduled")))
            if dep_dt is None:
                continue
            if arr_dt and arr_dt < dep_dt:
                arr_dt += timedelta(days=1)  # overnight arrival reported with same-day date

            # must be physically reachable from Iasi at all
            if dep_dt < earliest_leave + timedelta(hours=CHECKIN_BUFFER_H):
                continue

            airline = (entry.get("airline") or {}).get("name") or "Flight"
            code = (entry.get("flight") or {}).get("iata") or ""

            if legs is None:
                legs = _ground_legs(airport["city"], earliest_leave)

            deadline = dep_dt - timedelta(hours=CHECKIN_BUFFER_H)
            usable = [leg for leg in legs if leg.arrive <= deadline]
            best_leg = max(usable, key=lambda leg: leg.depart, default=None)

            if best_leg is not None:
                # full journey: bus/train out of Iasi -> flight from the nearby airport
                arrive = arr_dt or dep_dt
                out.append(Option(
                    mode="flight",
                    provider=f"{airline} from {airport['city']} (+ {best_leg.provider})",
                    depart=best_leg.depart,
                    arrive=arrive,
                    duration_h=round((arrive - best_leg.depart).total_seconds() / 3600, 1),
                    price_eur=best_leg.price_eur,  # flight fare unknown (no price in API)
                    transfers=1 + best_leg.transfers,
                    deep_link="https://www.google.com/travel/flights",
                    raw={
                        "flight_code": code,
                        "flight_departs": dep_dt.isoformat(),
                        "ground_provider": best_leg.provider,
                        "ground_price_eur": best_leg.price_eur,
                        "note": "price covers ground leg only",
                    },
                ))
            elif dep_dt >= earliest_leave + timedelta(hours=airport["ground_h_est"] + CHECKIN_BUFFER_H):
                # no scheduled ground leg fits, but a taxi/car ride still makes it
                out.append(Option(
                    mode="flight",
                    provider=f"{airline} (from {airport['city']})",
                    depart=dep_dt,
                    arrive=arr_dt,
                    duration_h=round((arr_dt - dep_dt).total_seconds() / 3600, 1) if arr_dt else None,
                    price_eur=None,
                    transfers=1,
                    deep_link="https://www.google.com/travel/flights",
                    raw={
                        "flight_code": code,
                        "ground_h": airport["ground_h_est"],
                        "note": "own transfer to the airport needed",
                    },
                ))

    return out


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    import config  # noqa: F401  (loads root .env for AVIATIONSTACK_API_KEY)

    f = Flight("Iasi", "LRIA", "Milano", "MXP",
               datetime.now().replace(hour=8, minute=0, second=0, microsecond=0))
    opts = nearby_flights_adapter(f)
    print(f"{len(opts)} nearby-airport options for {f.dest_city}:")
    for o in opts:
        print(f"  {o.provider:45} {o.depart:%H:%M}->{o.arrive:%H:%M} | t={o.transfers} | ~{o.price_eur} EUR")
    if not opts:
        print("  (none — AVIATIONSTACK_API_KEY not set, or no matching flights today)")
