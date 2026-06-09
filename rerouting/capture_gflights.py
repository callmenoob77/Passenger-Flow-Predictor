"""
capture_gflights.py — DEV ONLY
Refreshes gflights_cache.json by running the live Google Flights scraper
for the configured routes. Run manually before demo or when the cache is stale.

Requires adapter_gflights_live.py (the scraper), which is NOT committed to this
repo — gflights_cache.json already ships with pre-captured data for the demo.

Usage:
    python capture_gflights.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from resolver import Flight

try:
    from adapter_gflights_live import gflights_adapter
except ImportError:
    sys.exit(
        "capture_gflights.py needs the live Google Flights scraper "
        "(adapter_gflights_live.py), which is not part of this repo.\n"
        "gflights_cache.json already contains pre-captured demo data; "
        "to refresh it, add the scraper module first."
    )

CACHE_FILE = Path(__file__).parent / "gflights_cache.json"

# Routes of interest: (dest_city, dest_iata)
ROUTES = [
    ("Milano", "MXP"),
    ("Bergamo", "BGY"),
    ("London", "LTN"),
    ("Rome", "FCO"),
]

# Search for flights DAYS_AHEAD days from today
DAYS_AHEAD = 14


def _to_cache_row(o) -> dict:
    """Serialise an Option into the row format adapter_gflights_cached reads."""
    dur = o.duration_h or 0
    hh, mm = int(dur), round((dur % 1) * 60)
    return {
        "provider": o.provider,
        "from_city": o.raw.get("from_city", ""),
        "from_iata": o.raw.get("from_iata", ""),
        "date": o.depart.date().isoformat() if o.depart else None,
        "dep_str": o.depart.strftime("%I:%M %p on %a, %b %d") if o.depart else "",
        "arr_str": o.arrive.strftime("%I:%M %p on %a, %b %d") if o.arrive else "",
        "duration": f"{hh} hr {mm} min",
        "price_usd": f"${o.raw.get('price_usd', o.price_eur)}",
        "stops": o.raw.get("stops", o.transfers),
        "ground_h": o.raw.get("ground_h", 0.0),
    }


def main():
    departure = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=DAYS_AHEAD)
    cache = {}

    for dest_city, dest_iata in ROUTES:
        key = f"{dest_city.lower()}|{dest_iata}"
        print(f"  Capturing {dest_city} ({dest_iata})...")
        flight = Flight("Iasi", "IAS", dest_city, dest_iata, departure)
        opts = gflights_adapter(flight)
        cache[key] = [_to_cache_row(o) for o in opts]
        print(f"    -> {len(opts)} flights found")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"\nCache saved to {CACHE_FILE}")


if __name__ == "__main__":
    main()
