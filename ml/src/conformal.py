from __future__ import annotations

"""Split-conformal confidence wrapper for the fog classifier."""

import logging

import numpy as np
import pandas as pd

from src.config import setup_logging
from src.model import FogModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------

class ConformalWrapper:
    """Split-conformal prediction intervals for a binary fog classifier.

    Calibration: compute nonconformity scores |y_i - p_hat_i| on a held-out
    calibration split.  At test time, a (1-alpha) interval is
        [max(0, p - q), min(1, p + q)]
    where q is the (1-alpha) empirical quantile of calibration scores.
    This guarantees empirical coverage ≥ (1-alpha) by the exchangeability
    theorem (Venn-Abers / conformal prediction framework).
    """

    def __init__(self, base_model: FogModel, alpha: float = 0.20) -> None:
        self._model      = base_model
        self._alpha      = alpha         # target miscoverage rate
        self._quantile:  float | None = None

    def calibrate(self, X_cal: pd.DataFrame, y_cal: pd.Series) -> None:
        """Compute and store the conformal quantile from calibration data."""
        p_hat  = self._model.predict_proba(X_cal)
        scores = np.abs(y_cal.values - p_hat)        # nonconformity scores

        # Finite-sample corrected quantile: ceil((n+1)(1-alpha)) / n
        n                = len(scores)
        level            = np.ceil((n + 1) * (1 - self._alpha)) / n
        level            = min(level, 1.0)
        self._quantile   = float(np.quantile(scores, level))

        # Verify empirical coverage on calibration set
        lo   = np.clip(p_hat - self._quantile, 0, 1)
        hi   = np.clip(p_hat + self._quantile, 0, 1)
        cov  = np.mean((y_cal.values >= lo) & (y_cal.values <= hi))
        logger.info(
            "Conformal calibrated: alpha=%.2f  quantile=%.4f  empirical_coverage=%.3f (target %.3f)",
            self._alpha, self._quantile, cov, 1 - self._alpha,
        )

    def predict(
        self, X: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (point estimate, lower CI, upper CI) for each row."""
        if self._quantile is None:
            raise RuntimeError("Call calibrate() before predict()")
        p_hat = self._model.predict_proba(X)
        lo    = np.clip(p_hat - self._quantile, 0, 1)
        hi    = np.clip(p_hat + self._quantile, 0, 1)
        return p_hat, lo, hi


if __name__ == "__main__":
    from src.features import build_features
    from src.model    import LightGBMFog
    from src.splits   import make_splits
    setup_logging()

    fs    = build_features()
    split = make_splits(fs.X.index)
    fold  = split.folds[-1]   # use last fold for demo
    y     = fs.y["fog_in_2h"]

    X_tr, y_tr = fs.X.loc[fold.train_idx], y.loc[fold.train_idx]
    # Split val into fit-calibration and conformal-calibration halves
    mid        = len(fold.val_idx) // 2
    X_vl_fit,  y_vl_fit  = fs.X.loc[fold.val_idx[:mid]],  y.loc[fold.val_idx[:mid]]
    X_vl_cal,  y_vl_cal  = fs.X.loc[fold.val_idx[mid:]],  y.loc[fold.val_idx[mid:]]

    lgb = LightGBMFog()
    lgb.fit(X_tr, y_tr, X_vl_fit, y_vl_fit)

    wrapper = ConformalWrapper(lgb, alpha=0.20)
    wrapper.calibrate(X_vl_cal, y_vl_cal)

    p, lo, hi = wrapper.predict(X_vl_cal)
    print(f"Mean interval width: {(hi - lo).mean():.4f}")
    coverage = ((y_vl_cal.values >= lo) & (y_vl_cal.values <= hi)).mean()
    print(f"Empirical coverage:  {coverage:.3f}  (target 0.80)")
