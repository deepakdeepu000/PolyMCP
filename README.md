# MCP App Runbook

## What this project is

- A FastAPI app that accepts chat requests and uses MCP tool servers to fetch weather and flight/airport data.
- Two MCP servers run in the background: weather and flights. The app starts them automatically on startup.
- Redis is used as a cache for city/airport data (built on MCP server startup).

## Prerequisites

- Python 3.14+ (matches `pyproject.toml`).
- Redis running (WSL service or manual start).
- API keys in `.env`

## Environment (.env)

These settings are read from [mcp_app/config/settings.py](mcp_app/config/settings.py):

- `LLM_PROVIDER` (openai | gemini | ollama)
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `WEATHERAPI_KEY` (used by weather handler)
- `AERODATABOX_API_KEY` (used by flight handler)
- `WEATHER_MCP_URL` (optional, defaults to http://localhost:8001)
- `FLIGHTS_MCP_URL` (optional, defaults to http://localhost:8002)
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`

## Install

From repo root:

```bash
cd mcp_app
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Run Redis (WSL)

Option A (systemd enabled, auto-start):

```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

Option B (manual background start):

```bash
nohup redis-server >/tmp/redis.log 2>&1 &
```

## Run the app

From repo root:

```bash
cd mcp_app
uv run main.py
```

- The app starts the MCP servers automatically using [mcp_app/utils/tools/server_manager.py](mcp_app/utils/tools/server_manager.py).
- Weather MCP runs on `http://localhost:8001`.
- Flights MCP runs on `http://localhost:8002`.

## Test a request

Example:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"what are the available airports in hyderabad?\"}"
```

## How it works

1. [mcp_app/main.py](mcp_app/main.py) receives a chat request and builds messages for the LLM.
2. The LLM can request tool calls (MCP tools).
3. [mcp_app/mcp_client.py](mcp_app/mcp_client.py) sends MCP JSON-RPC tool calls over the server SSE session.
4. [mcp_app/utils/tools/server_manager.py](mcp_app/utils/tools/server_manager.py) keeps MCP servers alive and manages the SSE sessions.
5. Tool results are returned to the LLM and then summarized for the user.

## MCP tools and why they are used

Tools are defined in [mcp_app/utils/tools/tool_registry.py](mcp_app/utils/tools/tool_registry.py).

- `fetch_weather_data` (weather server)
  - Used for weather, air quality, and local time queries.
- `fetch_city_airports` (flights server)
  - Used to resolve a city to its airports, IATA codes, and metadata.
- `fetch_flight_data` (flights server)
  - Used for flight schedules or routing between two cities.

## MCP servers

- Weather MCP: [mcp_app/mcp_servers/weather_mcp/server.py](mcp_app/mcp_servers/weather_mcp/server.py)
- Flights MCP: [mcp_app/mcp_servers/airspace_mcp/server.py](mcp_app/mcp_servers/airspace_mcp/server.py)

## Redis cache

- The flights MCP server populates Redis at startup via:
  - [mcp_app/mcp_servers/airspace_mcp/helpers/build_redis.py](mcp_app/mcp_servers/airspace_mcp/helpers/build_redis.py)
- Cache keys:
  - `city:{CityName}`
  - `airport:iata:{IATA}`
  - `mcp:db_initialized`

## Common issues

- If tools time out, verify Redis and both MCP servers are running.
- If OpenAI/Gemini return 429/503, wait and retry or switch providers.
- If Redis is empty, rerun the flights MCP server to rebuild cache.
