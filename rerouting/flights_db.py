FLIGHT_DB = {
    # Original Demo Flights
    "RO 6769": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP"},
    "RO 6771": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Londra", "dest_icao": "LTN"},
    "RO 6773": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Roma", "dest_icao": "FCO"},
    "W6 1234": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bergamo", "dest_icao": "BGY"},
    "W6 2345": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP"},
    "FR 4321": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Londra", "dest_icao": "LTN"},
    "RO 707":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP"},

    # Real Flights from Iasi Airport (Departures)
    "A2 131":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP"},
    "A2 137":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP"},
    "OS 704":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Vienna", "dest_icao": "VIE"},
    "OS 706":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Vienna", "dest_icao": "VIE"},
    "H4 7551": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Hurghada", "dest_icao": "HRG"},
    "FR 3113": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bergamo", "dest_icao": "BGY"},
    "FR 3115": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Paris", "dest_icao": "BVA"},
    "RO 708":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP"},
    "W4 3667": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bologna", "dest_icao": "BLQ"},
    "W4 3639": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Basel", "dest_icao": "BSL"},
    "W4 3675": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Roma", "dest_icao": "FCO"},
    "W4 3697": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Liverpool", "dest_icao": "LPL"},
    "W4 3691": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Madrid", "dest_icao": "MAD"},
    "W4 3701": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP"},
    "W4 3669": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Venetia", "dest_icao": "TSF"},
}

def _normalize_key(s: str) -> str:
    return s.upper().replace("-", "").replace(" ", "").strip()

def _find_flight(flight_number: str):
    query = _normalize_key(flight_number)
    for k, v in FLIGHT_DB.items():
        if _normalize_key(k) == query:
            return k, v
    return None, None
