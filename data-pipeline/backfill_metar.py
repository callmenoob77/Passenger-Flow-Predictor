import io
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ---- CONFIG ----
CONN = "postgresql://postgres.tuqhlwpmhkirtvgihdxs:AdiDamianGebz@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"  # from Supabase Settings -> Database
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

# valid is UTC (we requested tz=Etc/UTC) but without timezone in the string -> mark explicitly as UTC
df["valid"] = pd.to_datetime(df["valid"]).dt.tz_localize("UTC")

# F -> C; vsby stays in miles (just renamed to vsby_mi)
df["tmpc"] = (df["tmpf"] - 32) * 5 / 9
df["dwpc"] = (df["dwpf"] - 32) * 5 / 9
df["vsby_mi"] = df["vsby"]
df["source"] = "backfill"

cols = ["station", "valid", "tmpc", "dwpc", "relh", "vsby_mi", "sknt",
        "drct", "alti", "mslp", "skyc1", "skyl1", "wxcodes", "metar", "source"]
out = df[cols].where(pd.notnull(df[cols]), None)  # NaN -> None for SQL NULL
rows = list(out.itertuples(index=False, name=None))

print("Inserting into Supabase...")
conn = psycopg2.connect(CONN)
cur = conn.cursor()
sql = f"""
    INSERT INTO metar_raw ({",".join(cols)})
    VALUES %s
    ON CONFLICT (station, valid) DO NOTHING
"""
execute_values(cur, sql, rows, page_size=1000)
conn.commit()

cur.execute("SELECT count(*), min(valid), max(valid) FROM metar_raw WHERE station = %s", (STATION,))
print("In DB now:", cur.fetchone())
cur.close()
conn.close()
print("Done.")