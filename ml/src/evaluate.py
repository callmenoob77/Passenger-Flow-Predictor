from __future__ import annotations

"""Walk-forward backtest report with bootstrap confidence intervals."""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

from src.config import SEED, get_config, setup_logging
from src.features import FeatureSet, build_features
from src.model import FogModel, LightGBMFog, LogRegFog, PersistenceFog
from src.splits import DataSplit, Fold, make_splits

logger = logging.getLogger(__name__)

# ---------------------------------------------------------

@dataclass
class HorizonMetrics:
    horizon:    str
    model:      str
    fold:       int
    pr_auc:     float
    pr_auc_ci:  tuple[float, float]
    brier:      float
    bss:        float
    bss_ci:     tuple[float, float]
    far:        float    # false alarm rate at strong-alert threshold
    n_pos:      int
    n_total:    int


def _bootstrap_ci(
    y_true:  np.ndarray,
    y_pred:  np.ndarray,
    metric:  str = "pr_auc",
    n_boot:  int = 500,
    alpha:   float = 0.10,
    rng:     np.random.Generator | None = None,
) -> tuple[float, float]:
    """Percentile bootstrap CI for pr_auc or bss."""
    if rng is None:
        rng = np.random.default_rng(SEED)
    scores = []
    clim   = y_true.mean()
    for _ in range(n_boot):
        idx = rng.integers(0, len(y_true), len(y_true))
        yt, yp = y_true[idx], y_pred[idx]
        if yt.sum() == 0:
            continue
        if metric == "pr_auc":
            scores.append(average_precision_score(yt, yp))
        else:  # bss
            b      = brier_score_loss(yt, yp)
            b_ref  = clim * (1 - clim)
            scores.append(1 - b / b_ref if b_ref > 0 else 0.0)
    lo = float(np.percentile(scores, 100 * alpha / 2))
    hi = float(np.percentile(scores, 100 * (1 - alpha / 2)))
    return lo, hi


def evaluate_fold(
    model:     FogModel,
    X_val:     pd.DataFrame,
    y_val:     pd.Series,
    horizon:   str,
    model_name: str,
    fold_num:  int,
) -> HorizonMetrics:
    cfg    = get_config()
    y_true = y_val.values
    y_pred = model.predict_proba(X_val)

    pr_auc = average_precision_score(y_true, y_pred) if y_true.sum() > 0 else float("nan")
    brier  = brier_score_loss(y_true, y_pred)
    clim   = y_true.mean()
    brier_ref = clim * (1 - clim)
    bss    = 1 - brier / brier_ref if brier_ref > 0 else 0.0

    # Bootstrap CIs
    pr_ci  = _bootstrap_ci(y_true, y_pred, "pr_auc")
    bss_ci = _bootstrap_ci(y_true, y_pred, "bss")

    # FAR at strong-alert threshold
    strong_thr = cfg.tiers.strong
    pred_pos   = (y_pred >= strong_thr)
    far        = float(((y_true == 0) & pred_pos).sum() / max(pred_pos.sum(), 1))

    logger.info(
        "  [%s | %s | fold %d] PR-AUC=%.3f [%.3f,%.3f]  BSS=%.3f [%.3f,%.3f]  FAR=%.3f",
        horizon, model_name, fold_num,
        pr_auc, pr_ci[0], pr_ci[1],
        bss,    bss_ci[0], bss_ci[1],
        far,
    )
    return HorizonMetrics(
        horizon   = horizon,
        model     = model_name,
        fold      = fold_num,
        pr_auc    = pr_auc,
        pr_auc_ci = pr_ci,
        brier     = brier,
        bss       = bss,
        bss_ci    = bss_ci,
        far       = far,
        n_pos     = int(y_true.sum()),
        n_total   = len(y_true),
    )


def run_backtest(
    fs:    FeatureSet | None = None,
    split: DataSplit  | None = None,
) -> pd.DataFrame:
    """Full walk-forward backtest across all horizons, models, and CV folds."""
    if fs    is None: fs    = build_features()
    if split is None: split = make_splits(fs.X.index)

    model_classes = {
        "lightgbm":    LightGBMFog,
        "logreg":      LogRegFog,
        "persistence": PersistenceFog,
    }

    all_metrics: list[HorizonMetrics] = []

    for horizon, y in fs.y.items():
        logger.info("── Horizon: %s ──", horizon)
        for fold in split.folds:
            X_tr = fs.X.loc[fold.train_idx]
            y_tr = y.loc[fold.train_idx]
            X_vl = fs.X.loc[fold.val_idx]
            y_vl = y.loc[fold.val_idx]

            if y_vl.sum() == 0:
                logger.warning("Fold %d %s: no positive examples in val — skipping", fold.fold, horizon)
                continue

            for name, cls in model_classes.items():
                m = cls()
                m.fit(X_tr, y_tr, X_vl, y_vl)
                metrics = evaluate_fold(m, X_vl, y_vl, horizon, name, fold.fold)
                all_metrics.append(metrics)

    rows = [
        {
            "horizon": m.horizon, "model": m.model, "fold": m.fold,
            "pr_auc": m.pr_auc, "pr_auc_lo": m.pr_auc_ci[0], "pr_auc_hi": m.pr_auc_ci[1],
            "brier": m.brier, "bss": m.bss, "bss_lo": m.bss_ci[0], "bss_hi": m.bss_ci[1],
            "far": m.far, "n_pos": m.n_pos, "n_total": m.n_total,
        }
        for m in all_metrics
    ]
    report = pd.DataFrame(rows)

    # Summary: mean ± std across folds per model/horizon
    if not report.empty:
        summary = (
            report.groupby(["horizon", "model"])[["pr_auc", "bss", "far"]]
            .agg(["mean", "std"])
            .round(4)
        )
        logger.info("\n%s", summary.to_string())

    return report


if __name__ == "__main__":
    setup_logging()
    report = run_backtest()
    print(report.to_string(index=False))
