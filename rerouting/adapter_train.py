"""
TRAIN Adapter (option 1) — STATIC CFR timetable from Iasi.
CFR has no API; the schedule is stable daily, so hardcoding is fine.

Routes covered:
  - Iasi -> Bucharest (the classic mainline IR/IC trains)
  - Iasi -> Bacau     (same Bucharest-bound trains, which call at Bacau)
  - Iasi -> Suceava   (separate line via Pascani)
Bacau and Suceava matter as ground legs to their airports when Iasi is fogged in.

!!! VERIFY departure times at https://bilete.cfrcalatori.ro
and fill them in below. Train numbers / durations / prices are realistic
(based on the official timetable), but the EXACT times need to be confirmed
so they are not made up.
"""

from datetime import datetime, timedelta
from resolver import Flight, Option

RON_TO_EUR = 0.20  # ~1 RON = 0.20 EUR (approximate; update if needed)

# (origin_city, dest_city) -> [(train_number, departure "HH:MM", duration_h, price_lei_class2)]
# The times below are PLACEHOLDERS — replace with real ones from bilete.cfrcalatori.ro
SCHEDULES = {
    ("iasi", "bucharest"): [
        ("IR 1661", "06:45", 6.5,  91.5),
        ("IC 561",  "13:10", 6.3,  91.5),
        ("IR 1663", "15:40", 6.55, 91.5),
        ("IR 1667", "23:30", 7.0,  91.5),   # night train
    ],
    # Bucharest-bound trains run via Pascani-Roman-Bacau: same departures, shorter leg
    ("iasi", "bacau"): [
        ("IR 1661", "06:45", 2.2, 45.0),
        ("IC 561",  "13:10", 2.1, 45.0),
        ("IR 1663", "15:40", 2.2, 45.0),
        ("IR 1667", "23:30", 2.3, 45.0),
    ],
    ("iasi", "suceava"): [
        ("IR 5631", "07:20", 2.4, 40.0),
        ("IR 5633", "12:10", 2.4, 40.0),
        ("IR 5635", "17:35", 2.4, 40.0),
    ],
}


def train_adapter(flight: Flight) -> list:
    schedule = SCHEDULES.get((flight.origin_city.lower(), flight.dest_city.lower()), [])

    base_date = flight.scheduled_departure.date()
    out = []
    for number, hhmm, dur_h, price_lei in schedule:
        h, m = map(int, hhmm.split(":"))
        depart = datetime(base_date.year, base_date.month, base_date.day, h, m)
        if depart <= flight.scheduled_departure:
            continue  # only trains departing after the cancelled flight
        arrive = depart + timedelta(hours=dur_h)
        out.append(Option(
            mode="train", provider=f"CFR {number}",
            depart=depart, arrive=arrive, duration_h=dur_h,
            price_eur=round(price_lei * RON_TO_EUR, 2),
            transfers=0,
            deep_link="https://bilete.cfrcalatori.ro/ro-RO/",
            raw={"train_number": number, "price_lei": price_lei},
        ))
    return out


if __name__ == "__main__":
    for dest in ("Bucharest", "Bacau", "Suceava"):
        f = Flight("Iasi", "LRIA", dest, "",
                   datetime.now().replace(hour=6, minute=0, second=0, microsecond=0))
        print(f"Trains {f.origin_city}->{dest} after {f.scheduled_departure:%H:%M}:")
        for o in train_adapter(f):
            print(f"  {o.provider:12} {o.depart:%H:%M}->{o.arrive:%H:%M} | {o.duration_h}h | ~{o.price_eur} EUR")
        print()
