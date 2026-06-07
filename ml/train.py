"""Training pipeline — BaggingClassifier with balanced DecisionTrees for fog nowcasting."""
from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import BaggingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import recall_score, precision_score, f1_score, brier_score_loss
from sklearn.tree import DecisionTreeClassifier

# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Config
# ---------------------------------------------------------
SEED              = 74
FOG_THRESHOLD_M   = 1000
PRIMARY_STATION   = "LRIA"
NEIGHBOR_STATIONS = ("LRSV", "LRBC", "LUKK")
ALL_STATIONS      = (PRIMARY_STATION,) + NEIGHBOR_STATIONS
HORIZON_HOURS     = 2
MERGE_TOLERANCE   = pd.Timedelta("40min")
MODEL_DIR         = Path("models")
IEM_URL           = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
START_DATE        = datetime(2016, 1, 1, tzinfo=timezone.utc)
END_DATE          = datetime.now(tz=timezone.utc)

# ---------------------------------------------------------
# 1. IEM METAR download
# ---------------------------------------------------------

def download_iem_station(
    station: str,
    start: datetime = START_DATE,
    end: datetime = END_DATE,
    retries: int = 3,
) -> pd.DataFrame:
    """Download METAR observations from Iowa Environmental Mesonet."""
    cache = Path("data") / "raw" / f"{station}_iem.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)

    if cache.exists():
        df = pd.read_parquet(cache)
        logger.info("%s: %d rows from cache", station, len(df))
        return df

    params = {
        "station":     station,
        "data":        "tmpf,dwpf,relh,drct,sknt,vsby,wxcodes",
        "year1": start.year,  "month1": start.month,  "day1": start.day,
        "year2": end.year,    "month2": end.month,    "day2": end.day,
        "tz":          "Etc/UTC",
        "format":      "comma",
        "latlon":      "no",
        "elev":        "no",
        "missing":     "M",
        "trace":       "T",
        "direct":      "no",
        "report_type": "3",
    }

    for attempt in range(1, retries + 1):
        try:
            logger.info("%s: IEM download attempt %d/%d", station, attempt, retries)
            resp = requests.get(IEM_URL, params=params, timeout=120)
            resp.raise_for_status()
            break
        except Exception as exc:
            logger.warning("%s: attempt %d failed: %s", station, attempt, exc)
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)

    # Parse CSV — skip comment lines starting with #
    lines = [ln for ln in resp.text.splitlines() if not ln.startswith("#")]
    if len(lines) < 2:
        logger.error("%s: IEM returned no data", station)
        return pd.DataFrame()

    df = pd.read_csv(StringIO("\n".join(lines)), na_values=["M", "T", ""])

    df["valid"] = pd.to_datetime(df["valid"], utc=True)
    df = df.sort_values("valid").reset_index(drop=True)

    # Convert Fahrenheit → Celsius
    for col in ("tmpf", "dwpf"):
        if col in df.columns:
            df[col] = (df[col].astype(float, errors="ignore") - 32) * 5 / 9

    # Convert visibility statute miles → metres
    if "vsby" in df.columns:
        df["vsby"] = pd.to_numeric(df["vsby"], errors="coerce") * 1609.344

    # Convert wind speed knots → m/s
    if "sknt" in df.columns:
        df["sknt"] = pd.to_numeric(df["sknt"], errors="coerce") * 0.514444

    # Rename
    rename = {
        "valid":   "time",
        "tmpf":    "temperature_c",
        "dwpf":    "dewpoint_c",
        "relh":    "humidity_pct",
        "drct":    "wind_dir_deg",
        "sknt":    "wind_speed_mps",
        "vsby":    "visibility_m",
        "wxcodes": "wxcodes",
    }
    df = df.rename(columns=rename)

    # Keep only needed columns
    keep = [c for c in rename.values() if c in df.columns]
    df = df[keep]

    # Ensure numeric types
    for c in ["temperature_c", "dewpoint_c", "humidity_pct", "wind_dir_deg",
              "wind_speed_mps", "visibility_m"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.set_index("time")
    df.to_parquet(cache)
    logger.info("%s: %d rows downloaded and cached", station, len(df))
    return df


def download_all_stations() -> dict[str, pd.DataFrame]:
    """Download data for all configured stations."""
    data = {}
    for station in ALL_STATIONS:
        df = download_iem_station(station)
        if not df.empty:
            data[station] = df
        else:
            logger.error("%s: no data — will be missing from alignment", station)
    return data


# ---------------------------------------------------------
# 2. Label computation
# ---------------------------------------------------------

def compute_labels(df: pd.DataFrame, horizon_h: int = HORIZON_HOURS) -> pd.Series:
    """Label: fog at LRIA T+horizon_h — visibility < 1000m OR wxcodes contains 'FG'."""
    vis_future = df["visibility_m"].shift(-horizon_h)
    fog_vis = (vis_future < FOG_THRESHOLD_M).astype(float)

    # Check wxcodes for FG
    if "wxcodes" in df.columns:
        wx_future = df["wxcodes"].shift(-horizon_h).fillna("")
        fog_wx = wx_future.str.contains("FG", case=False, na=False).astype(float)
        fog_label = ((fog_vis == 1) | (fog_wx == 1)).astype(float)
    else:
        fog_label = fog_vis

    fog_label.name = "fog_label"
    return fog_label


# ---------------------------------------------------------
# 3. Spatial alignment via merge_asof
# ---------------------------------------------------------

def align_stations(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Align neighbor stations to LRIA timeline using merge_asof (40min tolerance)."""
    primary = data[PRIMARY_STATION].copy()

    # Resample primary to hourly to get a clean grid
    primary = primary.resample("1h").first()
    primary = primary.dropna(subset=["visibility_m", "temperature_c", "dewpoint_c"])

    result = primary.copy()

    for station in NEIGHBOR_STATIONS:
        if station not in data:
            logger.warning("Neighbor %s not in data — skipping", station)
            continue

        nb = data[station].copy()
        prefix = station.lower()

        # Rename columns with station prefix
        nb_renamed = nb.rename(columns={
            c: f"{prefix}_{c}" for c in nb.columns if c != "wxcodes"
        })
        # Drop wxcodes from neighbors (only used for primary label)
        if "wxcodes" in nb.columns:
            nb_renamed = nb_renamed.drop(columns=["wxcodes"], errors="ignore")
        if f"{prefix}_wxcodes" in nb_renamed.columns:
            nb_renamed = nb_renamed.drop(columns=[f"{prefix}_wxcodes"], errors="ignore")

        # merge_asof requires sorted index
        nb_renamed = nb_renamed.sort_index()
        result = result.sort_index()

        result = pd.merge_asof(
            result,
            nb_renamed,
            left_index=True,
            right_index=True,
            tolerance=MERGE_TOLERANCE,
            direction="nearest",
        )

    logger.info("Aligned dataset: %d rows x %d columns", result.shape[0], result.shape[1])
    return result


# ---------------------------------------------------------
# 4. Feature engineering
# ---------------------------------------------------------

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create features: spread, humidity (Magnus), wind sin/cos, hour/month sin/cos."""
    f = pd.DataFrame(index=df.index)

    # Raw LRIA features
    f["visibility_m"]   = df["visibility_m"]
    f["temperature_c"]  = df["temperature_c"]
    f["dewpoint_c"]     = df["dewpoint_c"]
    f["wind_speed_mps"] = df.get("wind_speed_mps", pd.Series(np.nan, index=df.index))

    # Spread (dewpoint depression) — approaches 0 as fog forms
    f["spread"] = df["temperature_c"] - df["dewpoint_c"]

    # Relative humidity via Magnus formula
    t = df["temperature_c"]
    td = df["dewpoint_c"]
    # Magnus coefficients
    a, b = 17.27, 237.7
    gamma_t  = (a * t) / (b + t)
    gamma_td = (a * td) / (b + td)
    f["humidity_magnus"] = 100.0 * np.exp(gamma_td - gamma_t)
    f["humidity_magnus"] = f["humidity_magnus"].clip(0, 100)

    # Wind direction sin/cos
    wd = df.get("wind_dir_deg", pd.Series(np.nan, index=df.index))
    wd_rad = np.deg2rad(pd.to_numeric(wd, errors="coerce"))
    f["wind_dir_sin"] = np.sin(wd_rad)
    f["wind_dir_cos"] = np.cos(wd_rad)

    # Hour sin/cos (diurnal cycle)
    hour = df.index.hour
    f["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hour / 24)

    # Month sin/cos (seasonal cycle)
    month = df.index.month
    f["month_sin"] = np.sin(2 * np.pi * month / 12)
    f["month_cos"] = np.cos(2 * np.pi * month / 12)

    # Neighbor features — copy all prefixed columns
    for station in NEIGHBOR_STATIONS:
        prefix = station.lower()
        for col in df.columns:
            if col.startswith(f"{prefix}_"):
                f[col] = df[col]

    return f


# ---------------------------------------------------------
# 5. Chronological split (60/20/20)
# ---------------------------------------------------------

def chronological_split(
    X: pd.DataFrame, y: pd.Series
) -> tuple[
    pd.DataFrame, pd.Series,
    pd.DataFrame, pd.Series,
    pd.DataFrame, pd.Series,
]:
    """Strict chronological split: 60% train, 20% calibration, 20% test."""
    n = len(X)
    train_end = int(n * 0.60)
    cal_end   = int(n * 0.80)

    X_train, y_train = X.iloc[:train_end],        y.iloc[:train_end]
    X_cal,   y_cal   = X.iloc[train_end:cal_end],  y.iloc[train_end:cal_end]
    X_test,  y_test  = X.iloc[cal_end:],            y.iloc[cal_end:]

    logger.info(
        "Split: train=%d (%.0f%%)  cal=%d (%.0f%%)  test=%d (%.0f%%)",
        len(X_train), 100 * len(X_train) / n,
        len(X_cal), 100 * len(X_cal) / n,
        len(X_test), 100 * len(X_test) / n,
    )
    return X_train, y_train, X_cal, y_cal, X_test, y_test


# ---------------------------------------------------------
# 6. Model training (BaggingClassifier + balanced DecisionTree)
# ---------------------------------------------------------

def train_ensemble(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    n_estimators: int = 200,
) -> BaggingClassifier:
    """Train BaggingClassifier with balanced DecisionTrees."""
    base_tree = DecisionTreeClassifier(
        class_weight="balanced",
        max_depth=12,
        min_samples_leaf=10,
        random_state=SEED,
    )
    ensemble = BaggingClassifier(
        estimator=base_tree,
        n_estimators=n_estimators,
        max_samples=0.8,
        max_features=0.8,
        random_state=SEED,
        n_jobs=-1,
    )
    logger.info("Training BaggingClassifier with %d trees...", n_estimators)
    ensemble.fit(X_train, y_train)

    n_pos = int(y_train.sum())
    n_neg = int(len(y_train) - n_pos)
    logger.info("Training done: n_pos=%d  n_neg=%d  fog_rate=%.2f%%", n_pos, n_neg, 100 * n_pos / len(y_train))
    return ensemble


# ---------------------------------------------------------
# 7. Extract tree predictions (for calibration & uncertainty)
# ---------------------------------------------------------

def get_tree_predictions(ensemble: BaggingClassifier, X: pd.DataFrame) -> np.ndarray:
    """Get individual tree predictions — shape (n_samples, n_estimators).

    Each tree was trained on a feature subset (max_features=0.8), so we must
    index into X using estimators_features_ to match what each tree expects.
    """
    X_arr = X.values  # convert once to numpy for fast column indexing
    tree_preds = np.column_stack([
        est.predict_proba(X_arr[:, features])[:, 1]
        for est, features in zip(ensemble.estimators_, ensemble.estimators_features_)
    ])
    return tree_preds


# ---------------------------------------------------------
# 8. Calibration (Isotonic)
# ---------------------------------------------------------

def calibrate_model(
    ensemble: BaggingClassifier,
    X_cal: pd.DataFrame,
    y_cal: pd.Series,
) -> tuple[IsotonicRegression, IsotonicRegression, IsotonicRegression]:
    """Fit isotonic calibrators for mean, p10, and p90 of tree predictions."""
    tree_preds = get_tree_predictions(ensemble, X_cal)

    # Mean prediction (main calibrated probability)
    raw_mean = tree_preds.mean(axis=1)
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_mean, y_cal.values)

    # p10 (lower bound of uncertainty)
    raw_p10 = np.percentile(tree_preds, 10, axis=1)
    calibrator_lo = IsotonicRegression(out_of_bounds="clip")
    calibrator_lo.fit(raw_p10, y_cal.values)

    # p90 (upper bound of uncertainty)
    raw_p90 = np.percentile(tree_preds, 90, axis=1)
    calibrator_hi = IsotonicRegression(out_of_bounds="clip")
    calibrator_hi.fit(raw_p90, y_cal.values)

    logger.info("Isotonic calibration fitted on %d calibration rows", len(y_cal))
    return calibrator, calibrator_lo, calibrator_hi


# ---------------------------------------------------------
# 9. Alert thresholds (three-tier: silent / early_warning / full_risk)
# ---------------------------------------------------------

def _find_single_threshold(
    cal_probs: np.ndarray,
    y_cal: pd.Series,
    target_recall: float,
    label: str,
) -> float:
    """Find the best threshold achieving >= target_recall on calibration set."""
    best_threshold = 0.5
    best_f1 = -1.0

    for thr in np.arange(0.01, 0.99, 0.01):
        preds = (cal_probs >= thr).astype(int)
        rec = recall_score(y_cal, preds, zero_division=0)
        if rec >= target_recall:
            f1 = f1_score(y_cal, preds, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = float(thr)

    if best_f1 < 0:
        best_threshold = 0.02
        logger.warning("%s: no threshold achieves %.0f%% recall — defaulting to %.2f",
                       label, target_recall * 100, best_threshold)

    logger.info("%s threshold: %.2f (target recall >= %.0f%%)", label, best_threshold, target_recall * 100)
    return best_threshold


def find_alert_thresholds(
    ensemble: BaggingClassifier,
    calibrator: IsotonicRegression,
    X_cal: pd.DataFrame,
    y_cal: pd.Series,
) -> tuple[float, float]:
    """Compute two thresholds:
    - early_warning: high sensitivity (recall >= 0.95) — catches approaching advective fog
    - full_risk: balanced (recall >= 0.80) — imminent fog
    """
    tree_preds = get_tree_predictions(ensemble, X_cal)
    raw_mean = tree_preds.mean(axis=1)
    cal_probs = calibrator.predict(raw_mean)

    thr_early = _find_single_threshold(cal_probs, y_cal, target_recall=0.95, label="early_warning")
    thr_full  = _find_single_threshold(cal_probs, y_cal, target_recall=0.80, label="full_risk")

    # Ensure early_warning <= full_risk (early triggers first)
    if thr_early > thr_full:
        thr_early = thr_full

    return thr_early, thr_full


# ---------------------------------------------------------
# 10. Inference helpers (used by app.py too)
# ---------------------------------------------------------

def predict_with_calibration(
    ensemble: BaggingClassifier,
    calibrator: IsotonicRegression,
    calibrator_lo: IsotonicRegression,
    calibrator_hi: IsotonicRegression,
    X: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run inference: ensemble → calibrated prob, lo, hi."""
    tree_preds = get_tree_predictions(ensemble, X)

    raw_mean = tree_preds.mean(axis=1)
    raw_p10  = np.percentile(tree_preds, 10, axis=1)
    raw_p90  = np.percentile(tree_preds, 90, axis=1)

    prob    = calibrator.predict(raw_mean)
    prob_lo = calibrator_lo.predict(raw_p10)
    prob_hi = calibrator_hi.predict(raw_p90)

    # Ensure ordering: lo <= prob <= hi
    prob_lo = np.minimum(prob_lo, prob)
    prob_hi = np.maximum(prob_hi, prob)

    return prob, prob_lo, prob_hi


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Download
    logger.info("=" * 60)
    logger.info("STEP 1: Downloading IEM METAR data")
    logger.info("=" * 60)
    data = download_all_stations()

    if PRIMARY_STATION not in data:
        raise RuntimeError(f"Primary station {PRIMARY_STATION} has no data")

    # 2. Labels
    logger.info("=" * 60)
    logger.info("STEP 2: Computing fog labels (T+%dh)", HORIZON_HOURS)
    logger.info("=" * 60)
    primary_hourly = data[PRIMARY_STATION].resample("1h").first()
    labels = compute_labels(primary_hourly, HORIZON_HOURS)

    # 3. Spatial alignment
    logger.info("=" * 60)
    logger.info("STEP 3: Spatial alignment via merge_asof")
    logger.info("=" * 60)
    aligned = align_stations(data)

    # 4. Feature engineering
    logger.info("=" * 60)
    logger.info("STEP 4: Feature engineering")
    logger.info("=" * 60)
    X = engineer_features(aligned)

    # Align labels to feature index
    y = labels.reindex(X.index)

    # Drop wxcodes from features (it was only used for label)
    if "wxcodes" in X.columns:
        X = X.drop(columns=["wxcodes"])

    # Strict complete case
    mask = X.notna().all(axis=1) & y.notna()
    X = X[mask]
    y = y[mask]

    logger.info("After dropna: %d rows x %d features", X.shape[0], X.shape[1])
    logger.info("Fog rate: %.2f%% (%d positives)", 100 * y.mean(), int(y.sum()))

    if len(X) < 100:
        raise RuntimeError(f"Too few rows after alignment ({len(X)}). Check data.")

    # 5. Chronological split
    logger.info("=" * 60)
    logger.info("STEP 5: Chronological split (60/20/20)")
    logger.info("=" * 60)
    X_train, y_train, X_cal, y_cal, X_test, y_test = chronological_split(X, y)

    # 6. Train
    logger.info("=" * 60)
    logger.info("STEP 6: Training BaggingClassifier")
    logger.info("=" * 60)
    ensemble = train_ensemble(X_train, y_train)

    # 7. Calibrate
    logger.info("=" * 60)
    logger.info("STEP 7: Isotonic calibration + uncertainty")
    logger.info("=" * 60)
    calibrator, calibrator_lo, calibrator_hi = calibrate_model(ensemble, X_cal, y_cal)

    # 8. Alert thresholds (three-tier)
    logger.info("=" * 60)
    logger.info("STEP 8: Finding alert thresholds (early_warning + full_risk)")
    logger.info("=" * 60)
    thr_early, thr_full = find_alert_thresholds(ensemble, calibrator, X_cal, y_cal)

    # 9. Evaluate on test set
    logger.info("=" * 60)
    logger.info("STEP 9: Test set evaluation")
    logger.info("=" * 60)
    prob, prob_lo, prob_hi = predict_with_calibration(
        ensemble, calibrator, calibrator_lo, calibrator_hi, X_test
    )

    # Evaluate at full_risk threshold
    test_preds = (prob >= thr_full).astype(int)
    test_recall = recall_score(y_test, test_preds, zero_division=0)
    test_precision = precision_score(y_test, test_preds, zero_division=0)
    test_f1 = f1_score(y_test, test_preds, zero_division=0)
    test_brier = brier_score_loss(y_test, prob)
    mean_ci_width = float(np.mean(prob_hi - prob_lo))

    # Evaluate at early_warning threshold
    early_preds = (prob >= thr_early).astype(int)
    early_recall = recall_score(y_test, early_preds, zero_division=0)
    early_precision = precision_score(y_test, early_preds, zero_division=0)

    logger.info("--- full_risk (thr=%.2f) ---", thr_full)
    logger.info("  Recall:    %.3f", test_recall)
    logger.info("  Precision: %.3f", test_precision)
    logger.info("  F1:        %.3f", test_f1)
    logger.info("--- early_warning (thr=%.2f) ---", thr_early)
    logger.info("  Recall:    %.3f", early_recall)
    logger.info("  Precision: %.3f", early_precision)
    logger.info("--- general ---")
    logger.info("  Brier:     %.4f", test_brier)
    logger.info("  Mean CI:   %.4f", mean_ci_width)

    # 10. Save
    logger.info("=" * 60)
    logger.info("STEP 10: Saving artifacts")
    logger.info("=" * 60)

    joblib.dump(ensemble, MODEL_DIR / "ensemble.pkl")
    joblib.dump(calibrator, MODEL_DIR / "calibrator.pkl")
    joblib.dump(calibrator_lo, MODEL_DIR / "calibrator_lo.pkl")
    joblib.dump(calibrator_hi, MODEL_DIR / "calibrator_hi.pkl")

    # Save feature column order
    feature_cols = list(X.columns)
    with open(MODEL_DIR / "feature_cols.json", "w") as f:
        json.dump(feature_cols, f, indent=2)

    # Save metadata
    meta = {
        "horizon": f"{HORIZON_HOURS}h",
        "threshold_early_warning": thr_early,
        "threshold_full_risk": thr_full,
        "fog_threshold_m": FOG_THRESHOLD_M,
        "n_estimators": len(ensemble.estimators_),
        "n_train": len(X_train),
        "n_cal": len(X_cal),
        "n_test": len(X_test),
        "fog_rate_train": float(y_train.mean()),
        "fog_rate_test": float(y_test.mean()),
        "test_recall_full_risk": test_recall,
        "test_precision_full_risk": test_precision,
        "test_f1_full_risk": test_f1,
        "test_recall_early_warning": early_recall,
        "test_precision_early_warning": early_precision,
        "test_brier": test_brier,
        "mean_ci_width": mean_ci_width,
        "feature_count": len(feature_cols),
        "trained_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    with open(MODEL_DIR / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Saved: ensemble.pkl, calibrator*.pkl, feature_cols.json, meta.json")
    logger.info("Training pipeline complete!")


if __name__ == "__main__":
    main()
