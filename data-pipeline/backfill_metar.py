import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import io
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from config import CONN

# ---- CONFIG ----
STATION = "LRIA"
YEAR1, MONTH1, DAY1 = 2023, 6, 1      # start: 3 years back
YEAR2, MONTH2, DAY2 = 2026, 6, 7      # end: today
# ----------------

url = (
    "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
    f"?station={STATION}&data=all&tz=Etc/UTC&format=onlycomma"
    f"&latlon=no&missing=M&trace=T&direct=no"
    f"&year1={YEAR1}&month1={MONTH1}&day1={DAY1}"
    f"&year2={YEAR2}&month2={MONTH2}&day2={DAY2}"
)

print("Downloading from IEM...")
r = requests.get(url, timeout=300)
r.raise_for_status()

# 'M' = missing, 'T' = trace -> NaN
df = pd.read_csv(io.StringIO(r.text), na_values=["M", "T"])
print(f"{len(df)} raw rows.")

# Same column mapping as live_ingest.py — both scripts feed the same metar_raw table.
# valid is UTC (we requested tz=Etc/UTC) but without timezone in the string -> mark explicitly as UTC
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
df["source"]                 = "backfill"

cols = ["airport_icao", "observed_at", "temp_c", "dewpoint_c", "humidity_pct",
        "visibility_mi", "wind_speed_kt", "wind_dir_deg", "pressure_inhg",
        "sea_level_pressure_hpa", "cloud_cover", "cloud_base_ft",
        "weather_codes", "raw_metar", "source"]
out = df[cols].where(pd.notnull(df[cols]), None)  # NaN -> None for SQL NULL
rows = list(out.itertuples(index=False, name=None))

print("Inserting into Supabase...")
conn = psycopg2.connect(CONN)
cur = conn.cursor()
sql = f"""
    INSERT INTO metar_raw ({",".join(cols)})
    VALUES %s
    ON CONFLICT (airport_icao, observed_at) DO NOTHING
"""
execute_values(cur, sql, rows, page_size=1000)
conn.commit()

cur.execute("SELECT count(*), min(observed_at), max(observed_at) FROM metar_raw WHERE airport_icao = %s", (STATION,))
print("In DB now:", cur.fetchone())
cur.close()
conn.close()
print("Done.")