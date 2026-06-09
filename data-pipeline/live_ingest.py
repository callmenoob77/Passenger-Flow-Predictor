"""
Live ingest METAR LRIA: last 24 hours -> Supabase (metar_raw).
Runs on GitHub Actions every 15 min (the 24h window + ON CONFLICT DO NOTHING
makes it self-healing if a few runs are missed). Connection string comes from
env (GitHub Secret), NOT from code -> password never ends up in the repo.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import io
import os
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from config import CONN

STATION = "LRIA"

url = (
    "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
    f"?station={STATION}&data=all&tz=Etc/UTC&format=onlycomma"
    f"&latlon=no&missing=M&trace=T&direct=no&hours=24"
)

r = requests.get(url, timeout=120)
r.raise_for_status()

df = pd.read_csv(io.StringIO(r.text), na_values=["M", "T"])
if df.empty:
    print("No rows from IEM, exiting without error.")
    raise SystemExit(0)

# IEM -> descriptive names
df["airport_icao"]           = df["station"]
df["observed_at"]            = pd.to_datetime(df["valid"]).dt.tz_localize("UTC")
df["temp_c"]                 = (df["tmpf"] - 32) * 5 / 9
df["dewpoint_c"]             = (df["dwpf"] - 32) * 5 / 9
df["humidity_pct"]           = df["relh"]
df["visibility_mi"]          = df["vsby"]
df["wind_speed_kt"]          = df["sknt"]
df["wind_dir_deg"]           = df["drct"]
df["pressure_inhg"]          = df["alti"]
df["sea_level_pressure_hpa"] = df["mslp"]
df["cloud_cover"]            = df["skyc1"]
df["cloud_base_ft"]          = df["skyl1"]
df["weather_codes"]          = df["wxcodes"]
df["raw_metar"]              = df["metar"]
df["source"]                 = "live"

cols = ["airport_icao", "observed_at", "temp_c", "dewpoint_c", "humidity_pct",
        "visibility_mi", "wind_speed_kt", "wind_dir_deg", "pressure_inhg",
        "sea_level_pressure_hpa", "cloud_cover", "cloud_base_ft",
        "weather_codes", "raw_metar", "source"]
out = df[cols].where(pd.notnull(df[cols]), None)
rows = list(out.itertuples(index=False, name=None))

conn = psycopg2.connect(CONN)
cur = conn.cursor()
execute_values(
    cur,
    f"INSERT INTO metar_raw ({','.join(cols)}) VALUES %s "
    f"ON CONFLICT (airport_icao, observed_at) DO NOTHING",
    rows,
)
conn.commit()
cur.execute("SELECT count(*), max(observed_at) FROM metar_raw WHERE airport_icao = %s", (STATION,))
print(f"Processed {len(rows)} observations. In DB now:", cur.fetchone())
cur.close()
conn.close()
