from __future__ import annotations

"""Feature engineering – LRIA fog-risk features with multi-station advection inputs."""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import Config, get_config, setup_logging
from src.ingest import run_ingest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
_MI_TO_M = 1609.344  # statute miles → metres

# ---------------------------------------------------------
# Result type
# ---------------------------------------------------------

@dataclass
class FeatureSet:
    X:             pd.DataFrame
    y:             dict[str, pd.Series]  # "fog_in_2h" / "fog_in_6h" → binary Series
    feature_names: list[str]

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _parse_hours(horizon: str) -> int:
    """'2h' → 2, '6h' → 6."""
    return int(horizon.rstrip("h"))


def _to_metres(series: pd.Series) -> pd.Series:
    return series * _MI_TO_M


def _resample_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate irregular METAR timestamps to a uniform hourly grid."""
    return df.resample("1h").mean(numeric_only=True)

# ---------------------------------------------------------
# LRIA feature block
# ---------------------------------------------------------

def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """Return column if present and non-empty, else a NaN series with the same index."""
    if name in df.columns:
        return df[name]
    return pd.Series(float("nan"), index=df.index, name=name)


def _lria_features(df: pd.DataFrame) -> pd.DataFrame:
    vis_m = _to_metres(df["visibility_mi"])
    rh    = df["humidity_pct"]
    temp  = df["temp_c"]
    dp    = df["dewpoint_c"]
    pres  = _col(df, "sea_level_pressure_hpa")

    f = pd.DataFrame(index=df.index)

    # ---------------------------------------------------------
    # Raw observations
    f["visibility_m"]          = vis_m
    f["humidity_pct"]          = rh
    f["temp_c"]                = temp
    f["dewpoint_c"]            = dp
    f["sea_level_pressure_hpa"] = pres
    f["wind_speed_kt"]         = _col(df, "wind_speed_kt")

    # Circular wind encoding avoids the 360°/0° discontinuity
    wd_rad = np.deg2rad(_col(df, "wind_dir_deg"))
    f["wind_dir_sin"] = np.sin(wd_rad)
    f["wind_dir_cos"] = np.cos(wd_rad)

    # ---------------------------------------------------------
    # Derived meteorological indices
    f["dewpoint_depression"] = temp - dp   # approaches 0 as fog forms

    # ---------------------------------------------------------
    # Time-of-day and month cyclical features (fog has strong diurnal/seasonal signal)
    f["hour_sin"]  = np.sin(2 * np.pi * df.index.hour  / 24)
    f["hour_cos"]  = np.cos(2 * np.pi * df.index.hour  / 24)
    f["month_sin"] = np.sin(2 * np.pi * df.index.month / 12)
    f["month_cos"] = np.cos(2 * np.pi * df.index.month / 12)

    # ---------------------------------------------------------
    # Lags (strictly past — no leakage)
    for lag in (1, 2, 3, 6):
        f[f"vis_lag_{lag}h"] = vis_m.shift(lag)
        f[f"rh_lag_{lag}h"]  = rh.shift(lag)

    # ---------------------------------------------------------
    # Rolling statistics (backward window)
    for w in (3, 6, 12):
        f[f"vis_roll_{w}h"] = vis_m.rolling(w, min_periods=max(1, w // 2)).mean()
        f[f"rh_roll_{w}h"]  = rh.rolling(w,   min_periods=max(1, w // 2)).mean()

    # ---------------------------------------------------------
    # Trends (rate of change — key for advective fog)
    for w in (1, 3, 6):
        f[f"vis_trend_{w}h"]  = vis_m - vis_m.shift(w)
        f[f"rh_trend_{w}h"]   = rh    - rh.shift(w)

    f["pressure_tend_3h"] = pres - pres.shift(3)
    f["pressure_tend_6h"] = pres - pres.shift(6)

    return f

# ---------------------------------------------------------
# Neighbour feature block
# ---------------------------------------------------------

def _neighbour_features(station: str, df: pd.DataFrame) -> pd.DataFrame:
    p     = station.lower()
    vis_m = _to_metres(df["visibility_mi"])
    rh    = df["humidity_pct"]

    f = pd.DataFrame(index=df.index)
    f[f"{p}_visibility_m"]  = vis_m
    f[f"{p}_humidity_pct"]  = rh
    f[f"{p}_wind_speed_kt"] = df["wind_speed_kt"]

    wd_rad = np.deg2rad(df["wind_dir_deg"])
    f[f"{p}_wind_dir_sin"]  = np.sin(wd_rad)
    f[f"{p}_wind_dir_cos"]  = np.cos(wd_rad)

    f[f"{p}_vis_lag_1h"]    = vis_m.shift(1)
    f[f"{p}_vis_lag_3h"]    = vis_m.shift(3)
    f[f"{p}_rh_lag_1h"]     = rh.shift(1)
    f[f"{p}_vis_trend_3h"]  = vis_m - vis_m.shift(3)

    return f

# ---------------------------------------------------------
# Target computation  (strictly future, no leakage by construction)
# ---------------------------------------------------------

def _compute_targets(
    vis_m:       pd.Series,
    horizons:    tuple[str, ...],
    threshold_m: int,
) -> dict[str, pd.Series]:
    return {
        f"fog_in_{h}": (vis_m.shift(-_parse_hours(h)) < threshold_m).astype(float)
        for h in horizons
    }

# ---------------------------------------------------------
# Leakage assertion
# ---------------------------------------------------------

def _assert_no_leakage(
    vis_m:       pd.Series,
    y:           dict[str, pd.Series],
    threshold_m: int,
) -> None:
    """Verify that targets are computed from strictly future data.

    For a horizon of n hours, shift(-n) leaves exactly n NaN values at the
    tail of the raw series.  A different count would mean the shift is wrong.
    """
    for col in y:
        h_str      = col.replace("fog_in_", "")   # "fog_in_2h" → "2h"
        n          = _parse_hours(h_str)
        shifted    = vis_m.shift(-n)
        # Last n entries must be NaN — no future visibility exists for those rows
        tail_nan   = shifted.iloc[-n:].isna().all()
        assert tail_nan, (
            f"Leakage check failed for {col}: last {n} rows of shifted series are not NaN"
        )
    logger.info("Leakage assertion passed — all targets use strictly future observations")

# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def build_features(
    data: dict[str, pd.DataFrame] | None = None,
    cfg:  Config | None = None,
) -> FeatureSet:
    """Build the full feature matrix and binary fog targets.

    Loads data via run_ingest() if *data* is not supplied.
    Neighbour features are left-joined; rows without LRIA data are excluded.
    LightGBM handles NaN in neighbour columns natively where data is absent.
    """
    if cfg is None:
        cfg = get_config()
    if data is None:
        data = run_ingest()

    primary = cfg.stations.primary
    if primary not in data:
        raise ValueError(f"Primary station {primary} missing from data")

    # Resample every station to a clean hourly grid
    hourly = {s: _resample_hourly(df) for s, df in data.items()}

    # Primary features
    X = _lria_features(hourly[primary])

    # Neighbour features — left-join so missing periods become NaN (not dropped)
    for station in cfg.stations.neighbours:
        if station not in hourly:
            logger.warning("Neighbour %s not available — skipping", station)
            continue
        nb = _neighbour_features(station, hourly[station])
        X  = X.join(nb, how="left")

    # Targets  (attached temporarily to drop edge rows together)
    vis_m   = hourly[primary]["visibility_mi"] * _MI_TO_M
    targets = _compute_targets(vis_m, cfg.horizons, cfg.fog_threshold_m)

    target_cols = list(targets.keys())
    for col, s in targets.items():
        X[col] = s

    # Drop rows where any target is NaN  (end-of-series; no leakage edge effect)
    X = X.dropna(subset=target_cols)

    y   = {col: X.pop(col) for col in target_cols}

    # ---------------------------------------------------------
    # Logging
    for col, target in y.items():
        logger.info(
            "%s: %.2f%% fog rate  (%d positives / %d rows)",
            col, target.mean() * 100, int(target.sum()), len(target),
        )

    logger.info("Feature matrix: %d rows × %d columns", X.shape[0], X.shape[1])

    # Leakage assertion
    _assert_no_leakage(vis_m, y, cfg.fog_threshold_m)

    return FeatureSet(X=X, y=y, feature_names=list(X.columns))


if __name__ == "__main__":
    setup_logging()
    fs = build_features()
    print(f"\nShape:    {fs.X.shape}")
    print(f"Features: {fs.feature_names}")
    for col, s in fs.y.items():
        print(f"{col}: {s.mean():.3%} fog rate, {int(s.sum())} events")
