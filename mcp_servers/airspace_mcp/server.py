import sys
from contextlib import asynccontextmanager
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from utils.logging_setup import configure_logging

from handlers.fetch_city_airports import get_city_airport_data
from handlers.fetch_flight_data import fetch_flight_data
from helpers.build_redis import redis_store


@asynccontextmanager
async def lifespan(_: FastMCP):
    await redis_store()
    yield


airspaceMCP = FastMCP(
    name="AirspaceMCP",
    dependencies=["asyncio", "httpx", "redis"],
    lifespan=lifespan,
    port=8002,
)


@airspaceMCP.tool(
    name="fetch_flight_data",
    description="Fetches flight data for a given origin and destination city.",
)
async def fetch_flight_data_tool(origin: str, destination: str):
    return await fetch_flight_data(origin=origin, destination=destination)


@airspaceMCP.tool(
    name="fetch_city_airports",
    description="Fetches airport data for a given city name.",
)
async def fetch_city_airports_tool(city_name: str):
    return await get_city_airport_data(city_name=city_name)


@airspaceMCP.custom_route("/health", methods=["GET"])
async def health_check(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    configure_logging()
    airspaceMCP.run(transport="sse")
