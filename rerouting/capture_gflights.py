"""
capture_gflights.py — DEV ONLY
Refreshes gflights_cache.json by running live scrapers for the configured routes.
Run manually before demo or when the cache is stale.

Usage:
    python capture_gflights.py
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from adapter_gflights_cached import gflights_adapter
from resolver import Flight

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


def main():
    departure = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=DAYS_AHEAD)
    cache = {}

    for dest_city, dest_iata in ROUTES:
        key = f"{dest_city.lower()}|{dest_iata}"
        print(f"  Capturing {dest_city} ({dest_iata})...")
        flight = Flight("Iasi", "IAS", dest_city, dest_iata, departure)
        opts = gflights_adapter(flight)
        cache[key] = [
            {
                "provider": o.provider,
                "from_city": o.raw.get("from_city", ""),
                "depart": o.depart.isoformat() if o.depart else None,
                "arrive": o.arrive.isoformat() if o.arrive else None,
                "duration_h": o.duration_h,
                "price_eur": o.price_eur,
                "transfers": o.transfers,
                "deep_link": o.deep_link,
                "raw": o.raw,
            }
            for o in opts
        ]
        print(f"    -> {len(opts)} flights found")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"\nCache saved to {CACHE_FILE}")


if __name__ == "__main__":
    main()
