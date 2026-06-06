# SCHEMA — METAR Data

## Table `metar_raw`

| Column | Type | Description |
|---|---|---|
| `station_id` | TEXT | ICAO station code (e.g.: `LRIA`) |
| `observed_time` | TIMESTAMPTZ | Observation time (UTC) |
| `raw_text` | TEXT | Complete METAR message |
| `temp_c` | REAL | Temperature (°C) |
| `dewpoint_c` | REAL | Dew point (°C) |
| `wind_dir_deg` | INTEGER | Wind direction (degrees) |
| `wind_speed_kt` | INTEGER | Wind speed (knots) |
| `wind_gust_kt` | INTEGER | Gusts (knots), NULL if not reported |
| `visibility_m` | INTEGER | Visibility (meters) |
| `ceiling_ft` | INTEGER | Cloud ceiling (feet), NULL if CAVOK |
| `flight_category` | TEXT | VFR / MVFR / IFR / LIFR |
| `ingested_at` | TIMESTAMPTZ | Ingestion time into the database |

## Source

Aviation Weather Center — [https://aviationweather.gov/api/data/metar](https://aviationweather.gov/api/data/metar)

## Notes

- `backfill_metar.py` populates historical data (last N days).
- `live_ingest.py` runs periodically (cron / GitHub Actions) and adds new data.
