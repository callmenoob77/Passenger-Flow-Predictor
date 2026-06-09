# SCHEMA — METAR Data

## Table `metar_raw`

Populated by `backfill_metar.py` (historical) and `live_ingest.py` (every 15 min).
Both use the same column mapping; duplicates are skipped via
`ON CONFLICT (airport_icao, observed_at) DO NOTHING`.

| Column | Type | Description |
|---|---|---|
| `airport_icao` | TEXT | ICAO station code (e.g. `LRIA`) |
| `observed_at` | TIMESTAMPTZ | Observation time (UTC) |
| `temp_c` | REAL | Temperature (°C, converted from °F) |
| `dewpoint_c` | REAL | Dew point (°C, converted from °F) |
| `humidity_pct` | REAL | Relative humidity (%) |
| `visibility_mi` | REAL | Visibility (statute miles, as reported by IEM) |
| `wind_speed_kt` | REAL | Wind speed (knots) |
| `wind_dir_deg` | REAL | Wind direction (degrees) |
| `pressure_inhg` | REAL | Altimeter setting (inHg) |
| `sea_level_pressure_hpa` | REAL | Sea-level pressure (hPa), NULL if not reported |
| `cloud_cover` | TEXT | First sky-cover layer (e.g. `BKN`, `OVC`) |
| `cloud_base_ft` | REAL | Base of first cloud layer (feet) |
| `weather_codes` | TEXT | Present-weather codes (e.g. `FG`, `BR`) |
| `raw_metar` | TEXT | Complete raw METAR message |
| `source` | TEXT | `backfill` or `live` |

Unique constraint: `(airport_icao, observed_at)`.

## Source

Iowa Environmental Mesonet (IEM) ASOS download service —
[https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py](https://mesonet.agron.iastate.edu/request/download.phtml)

## Notes

- `backfill_metar.py` populates historical data (date range configured in the script).
- `live_ingest.py` runs every 15 min via GitHub Actions (`.github/workflows/ingest.yml`)
  and ingests the last 24 hours, deduplicated on conflict.
