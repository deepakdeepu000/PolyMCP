import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import FLIGHTS_MCP_URL, WEATHER_MCP_URL

# Centralized tool registry used by the LLM and MCP client orchestration.

MCP_SERVER_URLS: Dict[str, str] = {
    "weather": WEATHER_MCP_URL or "http://localhost:8001",
    "flights": FLIGHTS_MCP_URL or "http://localhost:8002",
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MCP_SERVER_START_SPECS: Dict[str, Dict[str, Any]] = {
    "weather": {
        "script": "mcp_servers/weather_mcp/server.py",
        "args": [],
    },
    "flights": {
        "script": "mcp_servers/airspace_mcp/server.py",
        "args": [],
    },
}


_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "fetch_weather_data",
        "description": (
            "Use this when the user asks about current weather in a specific city, "
            "including temperature, conditions (rain/clear), wind, humidity, visibility, "
            "air quality, or local time context. Good for questions like 'What's the weather in London?' "
            "or 'Is it raining in Delhi right now?'. "
            "IMPORTANT: Always pass the city name in Title Case (e.g., 'Vijayawada' not 'vijaywada', "
            "'New Delhi' not 'new delhi'). Use the standard English spelling."
        ),
        "server": "weather",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name in Title Case (e.g., 'London', 'Vijayawada', 'New Delhi').",
                },
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    },
    {
        "name": "fetch_city_airports",
        "description": (
            "Use this to look up city-to-airport metadata, IATA codes, and nearby airports. "
            "Helpful when the user mentions a city and needs airport identifiers or airport lists, "
            "or when you need to resolve a city name before searching flights. "
            "Good for questions like 'What airports are in Paris?' or 'What's the IATA code for Tokyo?' "
            "or 'list airports in New York' or 'What is the local time in Mumbai?'. "
            "NOTE: You do NOT need to call this before fetch_flight_data — "
            "fetch_flight_data accepts city names directly and resolves IATA codes internally."
        ),
        "server": "flights",
        "parameters": {
            "type": "object",
            "properties": {
                "city_name": {
                    "type": "string",
                    "description": "City name in Title Case (e.g., 'Delhi', 'New York', 'New Delhi').",
                },
            },
            "required": ["city_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "fetch_flight_data",
        "description": (
            "Use this when the user asks about flights between an origin and destination city, "
            "such as schedules, direct flights, or status for a date. "
            "Pass the origin and destination as plain city names in Title Case (e.g., 'New Delhi', 'Hyderabad') — "
            "do NOT pass IATA codes; the tool resolves them internally. "
            "Optionally include a travel date in YYYY-MM-DD format; if omitted, flights departing "
            "in the next 12 hours are returned. "
            "Good for: 'What flights are available from New York to London tomorrow?' "
            "IMPORTANT: Call this tool DIRECTLY with Title Case city names. "
            "Do NOT call fetch_city_airports first — that is unnecessary and wastes a round trip."
        ),
        "server": "flights",
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Origin city name in Title Case (e.g., 'New Delhi', 'Mumbai').",
                },
                "destination": {
                    "type": "string",
                    "description": "Destination city name in Title Case (e.g., 'Hyderabad', 'New York').",
                },
                "date": {
                    "type": "string",
                    "description": "Travel date in YYYY-MM-DD format. (optional, defaults to today)",
                },
            },
            "required": ["origin", "destination"],
            "additionalProperties": False,
        },
    },
]

def get_tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in _TOOL_DEFINITIONS
    ]


def get_tool_definition(name: str) -> Optional[Dict[str, Any]]:
    for tool in _TOOL_DEFINITIONS:
        if tool["name"] == name:
            return tool
    return None


def get_tool_definitions() -> List[Dict[str, Any]]:
    return list(_TOOL_DEFINITIONS)


def get_server_start_command(server_key: str) -> Optional[List[str]]:
    spec = MCP_SERVER_START_SPECS.get(server_key)
    if not spec:
        return None

    script_path = PROJECT_ROOT / spec.get("script", "")
    if not script_path.exists():
        return None

    args = spec.get("args") or []
    return [sys.executable, str(script_path), *args]