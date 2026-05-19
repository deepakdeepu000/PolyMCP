from typing import Optional, Dict, Any
from helpers.redis_cache import get_cache


async def get_city_airport_data(city_name: str) -> Dict[str, Any]:
    """Return normalized city data.

    Prefer provided `data` dict. If not provided, attempt to call a
    get_cache function (if available in globals()) with key "city:{city_name}".
    """
    
    try: 
        city_data = await get_cache(f"city:{city_name}")

        if not city_data:
            return {"error": f"No data found for city: {city_name}"}
        
        return {
                "name": city_data.get("city", "N/A"),
                "iata": city_data.get("city_code", "N/A"),
                "country": city_data.get("country", "N/A"),
                "coordinates": {
                    "latitude": city_data.get("latitude", "N/A"),
                    "longitude": city_data.get("longitude", "N/A")
                },
                "airports": [
                    {
                        "name": airport.get("airport_name", "N/A"),
                        "iata": airport.get("iata", "N/A"),
                        "icao": airport.get("icao", "N/A"),
                        "timezone": airport.get("timezone", "N/A")
                    }
                    for airport in city_data.get("airports", [])
                ],
            }

    except RuntimeError as e:
        return {"error": f"Cache/runtime error while fetching city data for '{city_name}': {e}"}
    except ValueError as e:
        return {"error": f"Invalid city data format for '{city_name}': {e}"}
    except KeyError as e:
        return {"error": f"Missing required field {e!s} in city data for '{city_name}'"}
        