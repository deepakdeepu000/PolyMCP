import asyncio
import json
from collections import defaultdict
from pathlib import Path
# from utils.redis_client.client import get_redis_client
from helpers.redis_cache import set_cache, get_cache


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CITIES_PATH = DATA_DIR / "cities.json"
AIRPORTS_PATH = DATA_DIR / "airports.json"

def normalize(text):
    return text.strip() if text else ""

async def _redis_store_sync():
    
    if await get_cache("mcp:db_initialized"):
        return
    
    with open(CITIES_PATH, "r", encoding="utf-8") as f:
        cities = json.load(f)["data"]

    with open(AIRPORTS_PATH, "r", encoding="utf-8") as f:
        airports = json.load(f)["data"]
    
    airport_groups = defaultdict(list)
    city_groups = defaultdict(list) 
    country_name_map = {}

    # ----------------------------
    # Process Airports
    # ----------------------------
    for a in airports:
        city_code = a.get("city_iata_code")
        country = normalize(a.get("country_name"))
        country_iso = a.get("country_iso2")
        iata = a.get("iata_code")

        if not iata or not city_code:
            continue

        country_name_map[country_iso] = country

        airport_obj = {
            "iata": iata,
            "airport_name": a.get("airport_name"),
            "latitude": float(a.get("latitude", 0)),
            "longitude": float(a.get("longitude", 0)),
            "timezone": a.get("timezone"),
        }

        airport_groups[city_code].append(airport_obj)

        # Store airport index
        await set_cache(f"airport:iata:{iata}", airport_obj)

    # ----------------------------
    # Process Cities
    # ----------------------------
    for c in cities:
        city_name = normalize(c.get("city_name"))
        city_code = c.get("iata_code")
        country_iso = c.get("country_iso2")

        if not city_name or not city_code:
            continue

        city_obj = {
            "city": city_name,
            "city_code": city_code,
            "country": country_name_map.get(country_iso, ""),
            "latitude": c.get("latitude"),
            "longitude": c.get("longitude"),
            "airports": airport_groups.get(city_code, [])
        }
        
        city_groups[city_name].append(city_obj)

        # Store city index
        await set_cache(f"city:{city_name}", city_obj)
    
    await set_cache("mcp:db_initialized", "true")
    
    with open(DATA_DIR / "city_airport_map.json", "w", encoding="utf-8") as f:
        json.dump(city_groups, f, ensure_ascii=False, indent=2)
        
async def redis_store() -> None:
    await _redis_store_sync()