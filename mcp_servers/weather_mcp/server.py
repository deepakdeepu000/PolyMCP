import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    # Ensure project root is on sys.path when loaded via mcp dev.
    sys.path.insert(0, str(project_root))
    

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from utils.logging_setup import configure_logging
from handlers.fetch_weather_data import fetch_weather_data

WeatherMCP = FastMCP(
    name="WeatherServer",
    dependencies=["asyncio", "httpx", "redis"],
    port=8001,
)

@WeatherMCP.tool(name="fetch_weather_data",
                 description="Fetches weather data for a given location and date. Expects a dictionary with 'location' and optional 'date' (YYYY-MM-DD) keys.")
async def weather_tool(city: str):
    return await fetch_weather_data(city=city)


@WeatherMCP.custom_route("/health", methods=["GET"])
async def health_check(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})

if __name__ == "__main__":
    configure_logging()
    WeatherMCP.run(transport="sse")