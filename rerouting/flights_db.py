FLIGHT_DB = {
    # Original Demo Flights
    "RO 6769": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP", "status": "FOG_RISK"},
    "RO 6771": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Londra", "dest_icao": "LTN", "status": "ON_TIME"},
    "RO 6773": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Roma", "dest_icao": "FCO", "status": "FOG_RISK"},
    "W6 1234": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bergamo", "dest_icao": "BGY", "status": "ON_TIME"},
    "W6 2345": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP", "status": "FOG_RISK"},
    "FR 4321": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Londra", "dest_icao": "LTN", "status": "ON_TIME"},
    "RO 707":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP", "status": "ON_TIME"},

    # Real Flights from Iasi Airport (Departures)
    "A2 131":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP", "status": "ON_TIME"},
    "A2 137":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP", "status": "ON_TIME"},
    "OS 704":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Vienna", "dest_icao": "VIE", "status": "FOG_RISK"},
    "OS 706":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Vienna", "dest_icao": "VIE", "status": "ON_TIME"},
    "H4 7551": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Hurghada", "dest_icao": "HRG", "status": "ON_TIME"},
    "FR 3113": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bergamo", "dest_icao": "BGY", "status": "FOG_RISK"},
    "FR 3115": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Paris", "dest_icao": "BVA", "status": "ON_TIME"},
    "RO 708":  {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bucharest", "dest_icao": "OTP", "status": "ON_TIME"},
    "W4 3667": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Bologna", "dest_icao": "BLQ", "status": "FOG_RISK"},
    "W4 3639": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Basel", "dest_icao": "BSL", "status": "ON_TIME"},
    "W4 3675": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Roma", "dest_icao": "FCO", "status": "FOG_RISK"},
    "W4 3697": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Liverpool", "dest_icao": "LPL", "status": "ON_TIME"},
    "W4 3691": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Madrid", "dest_icao": "MAD", "status": "ON_TIME"},
    "W4 3701": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Milano", "dest_icao": "MXP", "status": "FOG_RISK"},
    "W4 3669": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Venetia", "dest_icao": "TSF", "status": "ON_TIME"},

    # Additional Flights for Testing
    "W6 3703": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Barcelona", "dest_icao": "BCN", "status": "FOG_RISK"},
    "W4 3651": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Brussels", "dest_icao": "CRL", "status": "ON_TIME"},
    "FR 3117": {"origin_city": "Iasi", "origin_icao": "LRIA", "dest_city": "Dublin", "dest_icao": "DUB", "status": "FOG_RISK"},
}

def _normalize_key(s: str) -> str:
    return s.upper().replace("-", "").replace(" ", "").strip()

def _find_flight(flight_number: str):
    query = _normalize_key(flight_number)
    for k, v in FLIGHT_DB.items():
        if _normalize_key(k) == query:
            return k, v
    return None, None
