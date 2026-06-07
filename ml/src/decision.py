from __future__ import annotations

"""Tiered alert decision engine – maps calibrated probability → {strong / soft / silent}."""

import logging
from enum import Enum

import numpy as np

from src.config import TierConfig, get_config, setup_logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------

class Alert(str, Enum):
    STRONG = "strong"
    SOFT   = "soft"
    SILENT = "silent"


def classify_alert(prob: float, tiers: TierConfig | None = None) -> Alert:
    """Map a single probability to a tier label using config thresholds.

    Thresholds are read from config — changing config changes behaviour without
    touching this function.
    """
    if tiers is None:
        tiers = get_config().tiers
    if prob >= tiers.strong:
        return Alert.STRONG
    if prob >= tiers.soft:
        return Alert.SOFT
    return Alert.SILENT


def classify_batch(probs: np.ndarray, tiers: TierConfig | None = None) -> list[Alert]:
    """Vectorised version for arrays of probabilities."""
    if tiers is None:
        tiers = get_config().tiers
    return [classify_alert(float(p), tiers) for p in probs]


def optimal_thresholds(
    probs:  np.ndarray,
    labels: np.ndarray,
    cost_miss:   float = 5.0,
    cost_false:  float = 1.0,
) -> TierConfig:
    """Derive tier thresholds from cost asymmetry on a calibration set.

    Minimises expected cost = cost_miss * FN_rate + cost_false * FP_rate.
    Returns a TierConfig with the optimal strong threshold; soft is set to
    half the strong value as a heuristic starting point.
    """
    thresholds = np.linspace(0.01, 0.99, 200)
    best_cost  = float("inf")
    best_thr   = 0.5

    for thr in thresholds:
        pred      = (probs >= thr).astype(int)
        fn_rate   = ((labels == 1) & (pred == 0)).sum() / max((labels == 1).sum(), 1)
        fp_rate   = ((labels == 0) & (pred == 1)).sum() / max((labels == 0).sum(), 1)
        cost      = cost_miss * fn_rate + cost_false * fp_rate
        if cost < best_cost:
            best_cost = cost
            best_thr  = float(thr)

    soft_thr = round(best_thr / 2, 2)
    logger.info(
        "Optimal thresholds — strong: %.2f  soft: %.2f  (cost_miss=%.1f cost_false=%.1f)",
        best_thr, soft_thr, cost_miss, cost_false,
    )
    return TierConfig(strong=best_thr, soft=soft_thr)


if __name__ == "__main__":
    setup_logging()
    cfg = get_config()

    test_probs = [0.05, 0.45, 0.75, 0.35, 0.80]
    for p in test_probs:
        alert = classify_alert(p, cfg.tiers)
        print(f"  P={p:.2f} -> {alert.value}")
