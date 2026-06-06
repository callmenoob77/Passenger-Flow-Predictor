"""
TRAIN Adapter (option 1) — STATIC CFR timetable Iasi -> Bucharest.
CFR has no API; the schedule is stable daily, so hardcoding is fine.

!!! VERIFY departure times at https://bilete.cfrcalatori.ro (Iasi -> Bucharest Nord)
and fill them in below. Train numbers / durations / prices are real (from the official timetable),
but the EXACT times need to be confirmed by you so they are not made up.
"""

from datetime import datetime, timedelta
from resolver import Flight, Option

RON_TO_EUR = 0.20  # ~1 RON = 0.20 EUR (approximate; update if needed)

# Each train: (number, departure_time "HH:MM", duration_hours, price_lei_class2)
# The times below are PLACEHOLDERS — replace with real ones from bilete.cfrcalatori.ro
SCHEDULE = [
    ("IR 1661", "06:45", 6.5, 91.5),
    ("IC 561",  "13:10", 6.3, 91.5),
    ("IR 1663", "15:40", 6.55, 91.5),
    ("IR 1667", "23:30", 7.0, 91.5),   # night train
]

ROUTE = ("Iasi", "Bucharest")  # this adapter only covers this route


def train_adapter(flight: Flight) -> list:
    # this static adapter only knows the Iasi->Bucharest route
    if flight.origin_city.lower() != ROUTE[0].lower() or flight.dest_city.lower() != ROUTE[1].lower():
        return []

    base_date = flight.scheduled_departure.date()
    out = []
    for number, hhmm, dur_h, price_lei in SCHEDULE:
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
    f = Flight("Iasi", "LRIA", "Bucharest", "LROP",
               datetime.now().replace(hour=6, minute=0, second=0, microsecond=0))
    print(f"Trains {f.origin_city}->{f.dest_city} after {f.scheduled_departure:%H:%M}:\n")
    for o in train_adapter(f):
        print(f"  {o.provider:10} {o.depart:%H:%M}->{o.arrive:%H:%M} | {o.duration_h}h | ~{o.price_eur} EUR")