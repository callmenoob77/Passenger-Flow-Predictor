from __future__ import annotations

"""Multi-station METAR ingest – reads from Supabase metar_raw.
Neighbour stations (LRBC/LRSV/LUKK) are backfilled from IEM on first run if absent.
"""

import logging
import os
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

from src.config import get_config, setup_logging

logger = logging.getLogger(__name__)

load_dotenv()

# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------
_IEM_URL    = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
_IEM_FIELDS = ("tmpf", "dwpf", "relh", "drct", "sknt", "vsby", "mslp", "wxcodes")
_RAW_DIR    = Path("data") / "raw"
_PAGE_SIZE  = 1000  # Supabase PostgREST default max rows per request

_DEFAULT_START = datetime(2018, 1, 1, tzinfo=timezone.utc)
_DEFAULT_END   = datetime.now(tz=timezone.utc)

_IEM_RENAME = {
    "tmpf":    "temp_c",
    "dwpf":    "dewpoint_c",
    "relh":    "humidity_pct",
    "vsby":    "visibility_mi",
    "sknt":    "wind_speed_kt",
    "drct":    "wind_dir_deg",
    "mslp":    "sea_level_pressure_hpa",
    "wxcodes": "weather_codes",
}

_OUTPUT_COLS = list(_IEM_RENAME.values())

# ---------------------------------------------------------
# Supabase client
# ---------------------------------------------------------

def _client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_KEY must be set — copy .env.example to .env")
    return create_client(url, key)


def _row_count(station: str) -> int:
    resp = (
        _client()
        .table("metar_raw")
        .select("airport_icao", count="exact")
        .eq("airport_icao", station)
        .limit(0)
        .execute()
    )
    return resp.count or 0

# ---------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------

def _cache_path(station: str) -> Path:
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    return _RAW_DIR / f"{station}.parquet"


def _cache_valid(path: Path) -> bool:
    """True only if the cache was written by this module (Supabase-normalised schema)."""
    if not path.exists():
        return False
    try:
        cols = set(pd.read_parquet(path, columns=[]).columns)
        return "visibility_mi" in cols
    except Exception:
        return False

# ---------------------------------------------------------
# Supabase fetch  (paginated)
# ---------------------------------------------------------

def fetch_station(
    station: str,
    start: datetime = _DEFAULT_START,
    end: datetime   = _DEFAULT_END,
    *,
    force: bool = False,
) -> pd.DataFrame:
    """Read observations for *station* from Supabase; cache result locally.

    Paginates automatically (_PAGE_SIZE rows per request).
    Pass force=True to bypass the local cache and re-query Supabase.
    """
    cache = _cache_path(station)
    if _cache_valid(cache) and not force:
        df = pd.read_parquet(cache)
        logger.info("%s: %d rows from local cache", station, len(df))
        return df

    logger.info("%s: querying Supabase (paginated)", station)
    client  = _client()
    select  = ",".join(["observed_at"] + _OUTPUT_COLS)
    all_rows: list[dict] = []
    offset  = 0

    while True:
        resp = (
            client.table("metar_raw")
            .select(select)
            .eq("airport_icao", station)
            .gte("observed_at", start.isoformat())
            .lte("observed_at", end.isoformat())
            .order("observed_at")
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data
        all_rows.extend(batch)
        logger.debug("%s: fetched %d rows (offset %d)", station, len(batch), offset)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    if not all_rows:
        logger.warning("%s: 0 rows returned from Supabase", station)
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df = df.set_index("observed_at")
    df.index.name = "valid"

    # Supabase may return string 'NaN' in numeric columns instead of NULL
    df = df.replace("NaN", float("nan"))

    df.to_parquet(cache)
    logger.info("%s: %d rows → cached to %s", station, len(df), cache)
    return df

# ---------------------------------------------------------
# IEM → Supabase backfill  (runs once per missing station)
# ---------------------------------------------------------

def _fetch_iem(
    station: str,
    start: datetime,
    end: datetime,
    *,
    retries: int   = 3,
    backoff: float = 2.0,
) -> pd.DataFrame:
    params = {
        "station":     station,
        "data":        ",".join(_IEM_FIELDS),
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
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            logger.info("%s: IEM request (attempt %d/%d)", station, attempt, retries)
            resp = requests.get(_IEM_URL, params=params, timeout=90)
            resp.raise_for_status()
            lines = [ln for ln in resp.text.splitlines() if not ln.startswith("#")]
            if len(lines) < 2:
                return pd.DataFrame()
            df = pd.read_csv(StringIO("\n".join(lines)), na_values=["M", "T", ""])
            df["valid"] = pd.to_datetime(df["valid"], utc=True)
            return _iem_to_schema(df.sort_values("valid"), station)
        except Exception as exc:
            last_exc = exc
            logger.warning("%s: attempt %d failed: %s", station, attempt, exc)
            if attempt < retries:
                time.sleep(backoff ** attempt)
    raise RuntimeError(f"IEM fetch failed for {station} after {retries} attempts") from last_exc


def _iem_to_schema(df: pd.DataFrame, station: str) -> pd.DataFrame:
    df = df.rename(columns=_IEM_RENAME)
    for col in ("temp_c", "dewpoint_c"):
        if col in df.columns:
            df[col] = (df[col] - 32) * 5 / 9
    df["airport_icao"] = station
    df["source"]       = "iem_asos"
    df = df.rename(columns={"valid": "observed_at"})
    keep = ["airport_icao", "observed_at"] + _OUTPUT_COLS + ["source"]
    return df[[c for c in keep if c in df.columns]]


def backfill_station(
    station: str,
    start: datetime = _DEFAULT_START,
    end: datetime   = _DEFAULT_END,
) -> None:
    """Insert IEM observations for *station* into Supabase if the station is absent."""
    count = _row_count(station)
    if count > 0:
        logger.info("%s: %d rows already in Supabase — skipping backfill", station, count)
        return

    logger.info("%s: no data in Supabase — backfilling from IEM", station)
    df = _fetch_iem(station, start, end)
    if df.empty:
        logger.error("%s: IEM returned 0 rows", station)
        return

    # Use pandas JSON round-trip: handles NaN→null and Timestamp→ISO string
    import json
    records = json.loads(df.to_json(orient="records", date_format="iso", date_unit="s"))
    client  = _client()
    chunk   = 500  # stay well within PostgREST request-size limits

    for i in range(0, len(records), chunk):
        client.table("metar_raw").upsert(
            records[i : i + chunk],
            on_conflict="airport_icao,observed_at",
        ).execute()
        logger.debug("%s: upserted rows %d–%d", station, i, min(i + chunk, len(records)))

    logger.info("%s: inserted %d rows into Supabase", station, len(df))

# ---------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------

def run_ingest(
    start: datetime = _DEFAULT_START,
    end: datetime   = _DEFAULT_END,
    *,
    force_cache: bool = False,
) -> dict[str, pd.DataFrame]:
    """Backfill missing neighbour stations, then read all stations from Supabase."""
    cfg          = get_config()
    all_stations = (cfg.stations.primary,) + cfg.stations.neighbours

    if not force_cache:
        for station in cfg.stations.neighbours:
            try:
                backfill_station(station, start, end)
            except Exception as exc:
                logger.warning("%s: backfill failed (%s) — sarind peste", station, exc)

    results: dict[str, pd.DataFrame] = {}
    for station in all_stations:
        try:
            df = fetch_station(station, start, end, force=force_cache)
        except Exception as exc:
            # Daca Supabase nu e disponibil, incearca cache local
            cache = _cache_path(station)
            if _cache_valid(cache):
                logger.warning("%s: Supabase indisponibil, folosesc cache local", station)
                df = pd.read_parquet(cache)
            else:
                logger.error("%s: fetch failed si nu exista cache — %s", station, exc)
                continue
        if df.empty:
            logger.error("%s: 0 rows returned", station)
        else:
            results[station] = df

    logger.info("Ingest complete: %d/%d stations with data", len(results), len(all_stations))
    return results


if __name__ == "__main__":
    setup_logging()
    run_ingest()
