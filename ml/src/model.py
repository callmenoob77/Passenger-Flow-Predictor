from __future__ import annotations

"""LightGBM fog classifier with isotonic calibration + LogReg/persistence baselines.
Optional: conditional-visibility quantile head for multi-threshold queries (commit 6).
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.config import SEED, get_config, setup_logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Shared interface
# ---------------------------------------------------------

class FogModel(ABC):
    """All models expose a calibrated predict_proba interface."""

    @abstractmethod
    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val:   pd.DataFrame | None = None,
        y_val:   pd.Series   | None = None,
    ) -> None: ...

    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated P(fog) ∈ [0, 1] for each row."""
        ...

# ---------------------------------------------------------
# LightGBM  (primary model)
# ---------------------------------------------------------

class LightGBMFog(FogModel):
    """LightGBM with scale_pos_weight computed from train data, isotonic calibration on val."""

    def __init__(self) -> None:
        self._lgb:        LGBMClassifier    | None = None
        self._calibrator: IsotonicRegression | None = None

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val:   pd.DataFrame | None = None,
        y_val:   pd.Series   | None = None,
    ) -> None:
        n_neg            = int((y_train == 0).sum())
        n_pos            = int((y_train == 1).sum())
        scale_pos_weight = n_neg / n_pos   # derived from data — never a magic constant
        logger.info(
            "LightGBM fit: n_pos=%d  n_neg=%d  scale_pos_weight=%.2f",
            n_pos, n_neg, scale_pos_weight,
        )

        self._lgb = LGBMClassifier(
            n_estimators      = 500,
            learning_rate     = 0.05,
            num_leaves        = 63,
            min_child_samples = 20,
            subsample         = 0.8,
            colsample_bytree  = 0.8,
            reg_alpha         = 0.1,
            reg_lambda        = 1.0,
            scale_pos_weight  = scale_pos_weight,
            random_state      = SEED,
            n_jobs            = -1,
            verbose           = -1,
        )

        fit_kwargs: dict = {}
        if X_val is not None and y_val is not None:
            fit_kwargs["eval_set"] = [(X_val, y_val)]

        self._lgb.fit(X_train, y_train, **fit_kwargs)

        # Isotonic calibration on val set — a "70%" must mean ~70% empirically
        if X_val is not None and y_val is not None:
            raw_val          = self._lgb.predict_proba(X_val)[:, 1]
            self._calibrator = IsotonicRegression(out_of_bounds="clip")
            self._calibrator.fit(raw_val, y_val.values)
            logger.info("Isotonic calibrator fitted on %d val rows", len(y_val))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self._lgb is None:
            raise RuntimeError("Model not fitted — call fit() first")
        raw = self._lgb.predict_proba(X)[:, 1]
        if self._calibrator is not None:
            return self._calibrator.predict(raw)
        return raw

    def feature_importance(self, feature_names: list[str]) -> pd.Series:
        if self._lgb is None:
            raise RuntimeError("Model not fitted")
        return pd.Series(
            self._lgb.feature_importances_, index=feature_names,
        ).sort_values(ascending=False)

# ---------------------------------------------------------
# Logistic Regression baseline
# ---------------------------------------------------------

class LogRegFog(FogModel):
    """Logistic regression baseline — balanced class weights, standard scaling."""

    def __init__(self) -> None:
        self._scaler:  StandardScaler     = StandardScaler()
        self._medians: pd.Series | None   = None
        self._clf:     LogisticRegression = LogisticRegression(
            class_weight = "balanced",
            max_iter     = 1000,
            random_state = SEED,
        )

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val:   pd.DataFrame | None = None,
        y_val:   pd.Series   | None = None,
    ) -> None:
        # Drop columns that are entirely NaN in train (no signal, would break scaler)
        self._keep_cols = X_train.columns[X_train.notna().any()].tolist()
        Xt_raw          = X_train[self._keep_cols]
        self._medians   = Xt_raw.median()
        Xt = self._scaler.fit_transform(Xt_raw.fillna(self._medians))
        self._clf.fit(Xt, y_train)
        logger.info("LogReg baseline fitted on %d rows, %d features", len(y_train), len(self._keep_cols))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        Xt = self._scaler.transform(X[self._keep_cols].fillna(self._medians))
        return self._clf.predict_proba(Xt)[:, 1]

# ---------------------------------------------------------
# Persistence baseline
# ---------------------------------------------------------

class PersistenceFog(FogModel):
    """Baseline: current visibility < threshold → predict fog, else no fog."""

    def __init__(self) -> None:
        self._threshold_m: float = float(get_config().fog_threshold_m)

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val:   pd.DataFrame | None = None,
        y_val:   pd.Series   | None = None,
    ) -> None:
        logger.info("Persistence baseline: threshold %.0f m", self._threshold_m)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if "visibility_m" not in X.columns:
            raise ValueError("Persistence baseline requires 'visibility_m' column")
        return (X["visibility_m"] < self._threshold_m).astype(float).values

# ---------------------------------------------------------
# Optional: conditional-visibility head  (commit 6, behind flag)
# ---------------------------------------------------------

class VisibilityQuantileHead:
    """Distributional head for multi-threshold queries: P(vis < X) for any X.

    Uses LightGBM quantile regression — no upweight hack.
    This is the scalability stretch target; the binary classifier remains the
    default decision model.
    """

    # Quantiles to fit; covers the range of practical visibility thresholds
    _QUANTILES = (0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95)

    def __init__(self) -> None:
        self._regressors: dict[float, LGBMRegressor] = {}
        self._fitted = False

    def fit(self, X_train: pd.DataFrame, vis_train: pd.Series) -> None:
        """Fit one quantile regressor per quantile level."""
        for q in self._QUANTILES:
            reg = LGBMRegressor(
                objective    = "quantile",
                alpha        = q,
                n_estimators = 300,
                learning_rate= 0.05,
                num_leaves   = 31,
                random_state = SEED,
                n_jobs       = -1,
                verbose      = -1,
            )
            reg.fit(X_train, vis_train)
            self._regressors[q] = reg

        self._fitted = True
        logger.info("VisibilityQuantileHead fitted for %d quantiles", len(self._QUANTILES))

    def prob_below(self, X: pd.DataFrame, threshold_m: float) -> np.ndarray:
        """Return P(visibility < threshold_m) for each row using quantile interpolation."""
        if not self._fitted:
            raise RuntimeError("Call fit() first")

        quantiles = sorted(self._regressors)
        preds     = np.column_stack([
            self._regressors[q].predict(X) for q in quantiles
        ])  # shape: (n_samples, n_quantiles)

        # For each sample, interpolate CDF at threshold_m
        result = np.zeros(len(X))
        for i, row in enumerate(preds):
            # Monotone by construction (each quantile regressor independently fitted);
            # enforce monotonicity by sorting before interpolation
            sorted_row = np.sort(row)
            result[i]  = float(np.interp(threshold_m, sorted_row, quantiles))

        return result

# ---------------------------------------------------------
# Persistence
# ---------------------------------------------------------

MODELS: dict[str, type[FogModel]] = {
    "lightgbm":    LightGBMFog,
    "logreg":      LogRegFog,
    "persistence": PersistenceFog,
}


def save_model(model: object, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    joblib.dump(model, path)
    logger.info("Saved → %s", path)


def load_model(path: str) -> object:
    model = joblib.load(path)
    logger.info("Loaded ← %s", path)
    return model


if __name__ == "__main__":
    from src.features import build_features
    from src.splits   import make_splits
    setup_logging()

    fs    = build_features()
    split = make_splits(fs.X.index)
    fold  = split.folds[0]

    for horizon, y in fs.y.items():
        logger.info("── Horizon: %s ──", horizon)
        X_tr, y_tr = fs.X.loc[fold.train_idx], y.loc[fold.train_idx]
        X_vl, y_vl = fs.X.loc[fold.val_idx],   y.loc[fold.val_idx]

        for name, cls in MODELS.items():
            m = cls()
            m.fit(X_tr, y_tr, X_vl, y_vl)
            p = m.predict_proba(X_vl)
            logger.info("  %s: mean_pred=%.4f  fog_frac=%.3f", name, p.mean(), y_vl.mean())

        # Save primary model
        lgb = LightGBMFog()
        lgb.fit(X_tr, y_tr, X_vl, y_vl)
        save_model(lgb, f"models/lgb_{horizon}.pkl")

        # Optional head demo
        head = VisibilityQuantileHead()
        vis_train = fs.X.loc[fold.train_idx, "visibility_m"]
        head.fit(X_tr, vis_train)
        p_below = head.prob_below(X_vl, threshold_m=1000.0)
        logger.info("  quantile head: P(vis<1000m) mean=%.4f", p_below.mean())
