"""
Alternative Resolver (Component 6, Architecture 2).
Input: a cancelled flight. Output: top 3 ranked alternatives.

Adapter-based design: each source (flights, FlixBus, BlaBlaCar, CFR) is an adapter
that returns a list of Option objects in the SAME format. The resolver merges and sorts them.
If an adapter fails (API down, missing key), it's skipped -> the rest still work. The demo survives.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional
import traceback


@dataclass
class Flight:
    """The cancelled flight — resolver input."""
    origin_city: str           # e.g. "Iasi"
    origin_icao: str           # e.g. "LRIA"
    dest_city: str             # e.g. "Bucharest"
    dest_icao: str             # e.g. "LROP"
    scheduled_departure: datetime


@dataclass
class Option:
    """Common format returned by ALL adapters."""
    mode: str                  # "flight" | "bus" | "train" | "carpool"
    provider: str              # "Wizz Air" | "FlixBus" | "CFR" | "BlaBlaCar"
    depart: Optional[datetime]
    arrive: Optional[datetime]
    duration_h: Optional[float]
    price_eur: Optional[float]
    transfers: int = 0
    deep_link: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def delay_h(self, ref: datetime) -> float:
        if self.depart is None:
            return 999.0
        return max(0.0, (self.depart - ref).total_seconds() / 3600)


WEIGHTS = {"arrival": 1.0, "cost": 0.05, "transfers": 1.5}


def score(opt: Option, flight: Flight, weights=WEIGHTS) -> float:
    """Lower = better. Key metric: how late you ARRIVE at destination (not how late you depart)."""
    if opt.arrive is not None:
        arrival_lateness = max(0.0, (opt.arrive - flight.scheduled_departure).total_seconds() / 3600)
    elif opt.depart is not None:
        arrival_lateness = max(0.0, (opt.depart - flight.scheduled_departure).total_seconds() / 3600)
    else:
        arrival_lateness = 999.0
    cost = opt.price_eur if opt.price_eur is not None else 50.0
    return (weights["arrival"] * arrival_lateness
            + weights["cost"] * cost
            + weights["transfers"] * opt.transfers)


Adapter = Callable[[Flight], list]


MAX_GROUND_H = 10.0   # ground transport longer than this = absurd (e.g. bus Iasi->Milano 41h) -> remove it
MIN_DEPARTURE_GAP_H = 1.0  # minimum hours after the cancelled flight before an alternative can depart
                            # (notifications go out 2h before, passenger needs time to react)


def resolve(flight: Flight, adapters: list, top_n: int = 3) -> list:
    options = []
    for adapter in adapters:
        try:
            options.extend(adapter(flight))
        except Exception:
            print(f"[WARN] adapter {getattr(adapter, '__name__', adapter)} failed, skipping:")
            traceback.print_exc()
    # drop options that depart before a realistic reaction window
    min_depart = flight.scheduled_departure + timedelta(hours=MIN_DEPARTURE_GAP_H)
    options = [o for o in options if o.depart is None or o.depart >= min_depart]
    # ground transport to final destination only makes sense for reasonable distances
    options = [o for o in options
               if not (o.mode in ("bus", "train") and (o.duration_h or 0) > MAX_GROUND_H)]
    # dedupe identical journeys surfaced by multiple adapters
    # (e.g. cached Google-Flights vs live nearby-airport data) — keep the best-scored
    best: dict = {}
    for o in options:
        k = (o.mode, o.depart, o.arrive)
        if k not in best or score(o, flight) < score(best[k], flight):
            best[k] = o
    options = list(best.values())
    options.sort(key=lambda o: score(o, flight))
    return options[:top_n]


if __name__ == "__main__":
    def fake_adapter(flight):
        return [
            Option("bus", "FlixBus", datetime(2026, 6, 7, 14, 0),
                   datetime(2026, 6, 7, 22, 0), 8.0, 25.0, transfers=0),
            Option("flight", "Wizz Air", datetime(2026, 6, 7, 18, 0),
                   datetime(2026, 6, 7, 19, 0), 1.0, 90.0, transfers=0),
            Option("train", "CFR", datetime(2026, 6, 7, 12, 0),
                   datetime(2026, 6, 8, 0, 30), 12.5, 30.0, transfers=1),
        ]

    f = Flight("Iasi", "LRIA", "Bucharest", "LROP", datetime(2026, 6, 7, 10, 0))
    for i, opt in enumerate(resolve(f, [fake_adapter]), 1):
        print(f"{i}. {opt.mode:7} {opt.provider:10} departs {opt.depart.strftime('%H:%M')} "
              f"| {opt.duration_h}h | {opt.price_eur}EUR | score={score(opt, f):.1f}")