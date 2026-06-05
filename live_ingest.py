"""
Live ingest METAR LRIA: ultimele 3 ore -> Supabase (metar_raw).
Ruleaza pe GitHub Actions la 15 min. Connection string vine din env (GitHub Secret),
NU din cod -> parola nu ajunge niciodata in repo.
"""

import io
import os
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

CONN = "postgresql://postgres.tuqhlwpmhkirtvgihdxs:AdiDamianGebz@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"  # din Supabase Settings -> Database# setat ca GitHub Secret
STATION = "LRIA"

url = (
    "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
    f"?station={STATION}&data=all&tz=Etc/UTC&format=onlycomma"
    f"&latlon=no&missing=M&trace=T&direct=no&hours=3"
)

r = requests.get(url, timeout=120)
r.raise_for_status()

df = pd.read_csv(io.StringIO(r.text), na_values=["M", "T"])
if df.empty:
    print("Niciun rand de la IEM, ies fara eroare.")
    raise SystemExit(0)

df["valid"] = pd.to_datetime(df["valid"]).dt.tz_localize("UTC")
df["tmpc"] = (df["tmpf"] - 32) * 5 / 9
df["dwpc"] = (df["dwpf"] - 32) * 5 / 9
df["vsby_mi"] = df["vsby"]
df["source"] = "live"

cols = ["station", "valid", "tmpc", "dwpc", "relh", "vsby_mi", "sknt",
        "drct", "alti", "mslp", "skyc1", "skyl1", "wxcodes", "metar", "source"]
out = df[cols].where(pd.notnull(df[cols]), None)
rows = list(out.itertuples(index=False, name=None))

conn = psycopg2.connect(CONN)
cur = conn.cursor()
execute_values(
    cur,
    f"INSERT INTO metar_raw ({','.join(cols)}) VALUES %s "
    f"ON CONFLICT (station, valid) DO NOTHING",
    rows,
)
conn.commit()
cur.execute("SELECT count(*), max(valid) FROM metar_raw WHERE station = %s", (STATION,))
print(f"Procesate {len(rows)} obs. In DB acum:", cur.fetchone())
cur.close()
conn.close()