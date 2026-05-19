import asyncio
import logging
import json
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from config.settings import AERODATABOX_API_KEY
from helpers.redis_cache import get_cache

logger = logging.getLogger(__name__)


def simplify_flight_info(flight: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalises complex API data into a flat, token-efficient
    dictionary optimised for LLM reasoning.
    """
    departure = flight.get("departure", {})
    arrival = flight.get("arrival", {})

    return {
        "flight_identity": f"{flight.get('airline', {}).get('name')} {flight.get('number')}",
        "status": flight.get("status", "Unknown"),
        "departure": {
            "local_time": departure.get("scheduledTime", {}).get("local", "N/A"),
            "terminal": departure.get("terminal", "N/A"),
            "gate": departure.get("gate", "N/A"),
            "is_delayed": departure.get("delay") is not None,
        },
        "arrival": {
            "airport": arrival.get("airport", {}).get("name", "N/A"),
            "scheduled_local": arrival.get("scheduledTime", {}).get("local", "N/A"),
            "terminal": arrival.get("terminal", "N/A"),
        },
        "aircraft": flight.get("aircraft", {}).get("model", "Data Unavailable"),
        "airline": flight.get("airline", {}).get("name", "N/A"),
    }


async def fetch_flight_data(
    origin: str,
    destination: str,
    date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Get and clean flight options between two cities.

    Args:
        origin: Origin city name.
        destination: Destination city name.
        date: Optional travel date. Defaults to a 12-hour window starting now.
    """
    logger.info("Fetching flight data: %s -> %s on %s", origin, destination, date)

    origin_data = await get_cache(f"city:{origin}")
    destination_data = await get_cache(f"city:{destination}")

    origin_iatas: List[str] = [
        a.get("iata") for a in (origin_data.get("airports") or []) if a.get("iata")
    ]
    destination_iatas: List[str] = [
        a.get("iata") for a in (destination_data.get("airports") or []) if a.get("iata")
    ]

    if not origin_iatas or not destination_iatas:
        return {"error": "Unable to find IATA codes for the provided cities."}

    if set(origin_iatas) & set(destination_iatas):
        return {"error": "Origin and destination cannot be the same (overlapping airports)."}

    now = datetime.now()
    future_date = date is not None and date.date() != now.date()

    if future_date:
        base_date = date.date()
        day_start = datetime.combine(base_date, datetime.min.time())
        windows = [
            (day_start, day_start + timedelta(hours=12)),
            (day_start + timedelta(hours=12, minutes=30), day_start + timedelta(hours=23, minutes=30)),
        ]
    else:
        start_time = (now + timedelta(hours=2)).replace(second=0, microsecond=0)
        windows = [(start_time, start_time + timedelta(hours=12))]

    headers = {
        "Accept": "application/json, application/xml",
        "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com",
        "X-RapidAPI-Key": AERODATABOX_API_KEY,
    }
    params = {
        "direction": "Departure",
        "withLeg": "true",
        "withCodeshared": "true",
    }

    try:
        all_departures: List[Dict[str, Any]] = []

        async with httpx.AsyncClient() as client:
            for window_start, window_end in windows:
                time_start = window_start.strftime("%Y-%m-%dT%H:%M")
                time_end = window_end.strftime("%Y-%m-%dT%H:%M")

                for origin_iata in origin_iatas:
                    url = (
                        f"https://aerodatabox.p.rapidapi.com/flights/airports/Iata"
                        f"/{origin_iata}/{time_start}/{time_end}"
                    )

                    response = await client.get(url, headers=headers, params=params)

                    if response.status_code == 204:
                        await asyncio.sleep(1)
                        continue

                    response.raise_for_status()
                    flights_data = response.json()

                    if "error" in flights_data or "message" in flights_data:
                        error_msg = flights_data.get("message") or flights_data.get("error", "")
                        if "not authorized" in error_msg.lower() or "plan" in error_msg.lower():
                            return {
                                "error": f"API Authorization Failed: {error_msg}",
                                "details": "Check RapidAPI key and subscription plan",
                            }

                    all_departures.extend(flights_data.get("departures", []))
                    await asyncio.sleep(3)  # respect rate limits

        origin_iata_str = ", ".join(origin_iatas)
        destination_iata_str = ", ".join(destination_iatas)

        if not all_departures:
            return {
                "summary": f"No flights found from {origin_iata_str} to {destination_iata_str} for the requested time window.",
                "flights": [],
            }

        filtered_flights = [
            simplify_flight_info(flight)
            for flight in all_departures
            if flight.get("arrival", {}).get("airport", {}).get("iata") in destination_iatas
        ]

        return {
            "query_summary": f"Direct flights from {origin_iata_str} to {destination_iata_str}",
            "time_window": " | ".join(
                f"{ws.strftime('%H:%M')} to {we.strftime('%H:%M')}"
                for ws, we in windows
            ),
            "flights": filtered_flights or "No direct flights found in the specified time window.",
            "count": len(filtered_flights),
        }

    except httpx.HTTPStatusError as e:
        return {"error": f"API Error: {e.response.status_code}", "details": e.response.text}
    except Exception as e:
        logger.exception("Unexpected error in fetch_flight_data")
        return {"error": f"Internal error: {str(e)}"}
