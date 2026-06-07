from __future__ import annotations

"""Time-based train/validation/test splits – strictly chronological."""

import logging
from dataclasses import dataclass

import pandas as pd

from src.config import CVConfig, get_config, setup_logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------

@dataclass
class Fold:
    fold:      int
    train_idx: pd.DatetimeIndex
    val_idx:   pd.DatetimeIndex


@dataclass
class DataSplit:
    folds:    list[Fold]
    test_idx: pd.DatetimeIndex


def make_splits(
    index: pd.DatetimeIndex,
    cv:    CVConfig | None = None,
) -> DataSplit:
    """Expanding-window purged walk-forward CV + chronological holdout test set.

    Timeline:  [──────── CV folds (80%) ────────|gap|── test (20%) ──]
    Fold k trains on all data up to block k and validates on block k+1.
    A gap_days purge boundary prevents label leakage across the fold edge.
    """
    if cv is None:
        cv = get_config().cv

    index = index.sort_values()
    n     = len(index)

    # Fixed holdout: last 20% of the timeline
    cutoff   = index[int(n * 0.8)]
    test_idx = index[index >= cutoff]
    cv_idx   = index[index <  cutoff]

    # Divide CV range into (n_splits + 1) equally-spaced time boundaries
    boundaries = pd.date_range(cv_idx[0], cv_idx[-1], periods=cv.n_splits + 2)
    gap        = pd.Timedelta(days=cv.gap_days)
    folds: list[Fold] = []

    for k in range(cv.n_splits):
        train_end = boundaries[k + 1]
        val_start = train_end + gap
        val_end   = boundaries[k + 2]

        # Expanding train window: all CV data up to train_end
        train_idx = cv_idx[cv_idx < train_end]
        val_idx   = cv_idx[(cv_idx >= val_start) & (cv_idx < val_end)]

        if len(train_idx) == 0 or len(val_idx) == 0:
            logger.warning("Fold %d skipped — empty train or val", k + 1)
            continue

        folds.append(Fold(fold=k + 1, train_idx=train_idx, val_idx=val_idx))

    # ---------------------------------------------------------
    # Assertions: no train/val overlap within any fold; val windows are ordered
    assert len(folds) >= 3, f"Need ≥3 CV folds, got {len(folds)}"

    for f in folds:
        assert f.train_idx.max() < f.val_idx.min(), (
            f"Fold {f.fold}: train end overlaps val start"
        )

    for i in range(len(folds) - 1):
        assert folds[i].val_idx.max() < folds[i + 1].val_idx.min(), (
            f"Val windows of folds {i+1} and {i+2} are not strictly ordered"
        )

    logger.info(
        "CV: %d folds | test holdout: %d rows (%s → %s)",
        len(folds), len(test_idx),
        test_idx[0].date(), test_idx[-1].date(),
    )
    for f in folds:
        logger.info(
            "  Fold %d: train %d rows (%s→%s)  val %d rows (%s→%s)",
            f.fold,
            len(f.train_idx), f.train_idx[0].date(), f.train_idx[-1].date(),
            len(f.val_idx),   f.val_idx[0].date(),   f.val_idx[-1].date(),
        )

    return DataSplit(folds=folds, test_idx=test_idx)


if __name__ == "__main__":
    from src.features import build_features
    setup_logging()
    fs    = build_features()
    split = make_splits(fs.X.index)
    print(f"\n{len(split.folds)} folds, {len(split.test_idx)} test rows")
