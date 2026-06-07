from __future__ import annotations

"""Central project configuration – single source of truth for all meteorological and model parameters."""

import logging
import pprint
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------
SEED: int = 74

# ---------------------------------------------------------
# Fog definition — change here to retarget minima
# ---------------------------------------------------------
FOG_THRESHOLD_M: int = 1000  # visibility below this (metres) → fog label

# ---------------------------------------------------------
# Forecast horizons
# ---------------------------------------------------------
HORIZONS: tuple[str, ...] = ("2h", "6h")

# ---------------------------------------------------------
# Station list
# ---------------------------------------------------------
@dataclass(frozen=True)
class StationConfig:
    primary:    str            = "LRIA"
    # Upstream / neighbour stations for advection features.
    # Validated against IEM ASOS availability; extend via config, no code change.
    neighbours: tuple[str, ...] = ("LRBC", "LRSV", "LUKK")


# ---------------------------------------------------------
# Walk-forward CV parameters
# ---------------------------------------------------------
@dataclass(frozen=True)
class CVConfig:
    n_splits:     int = 5   # number of rolling-origin folds
    train_months: int = 18  # training window length per fold
    gap_days:     int = 2   # purge gap — prevents temporal leakage across boundary


# ---------------------------------------------------------
# Tier alert thresholds  (placeholder — cost-function derived in commit 8)
# ---------------------------------------------------------
@dataclass(frozen=True)
class TierConfig:
    strong: float = 0.70  # placeholder; will be tuned from cost matrix
    soft:   float = 0.40  # placeholder; will be tuned from cost matrix


# ---------------------------------------------------------
# Master config
# ---------------------------------------------------------
@dataclass(frozen=True)
class Config:
    seed:            int           = SEED
    fog_threshold_m: int           = FOG_THRESHOLD_M
    horizons:        tuple[str, ...] = field(default_factory=lambda: HORIZONS)
    stations:        StationConfig   = field(default_factory=StationConfig)
    cv:              CVConfig        = field(default_factory=CVConfig)
    tiers:           TierConfig      = field(default_factory=TierConfig)


def get_config() -> Config:
    """Return the resolved project configuration."""
    cfg = Config()
    logger.debug(
        "Config resolved: seed=%d  fog_threshold_m=%d  horizons=%s  stations=%s",
        cfg.seed, cfg.fog_threshold_m, cfg.horizons, cfg.stations,
    )
    return cfg


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger; call once from each module's __main__ block."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


if __name__ == "__main__":
    setup_logging(logging.DEBUG)
    cfg = get_config()
    pprint.pprint(cfg)
