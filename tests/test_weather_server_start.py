"""
Integration test: starts the weather MCP server, runs a health check,
calls the fetch_weather_data tool, and prints the result.
"""

import asyncio
import json
import time

from utils.logging_setup import configure_logging
from utils.tools.server_manager import ensure_server, get_session, wait_for_message, shutdown_all_servers


def main() -> None:
    configure_logging()
    asyncio.run(_test())


async def _test() -> None:
    try:
        await ensure_server("weather")
        session = get_session("weather")
        if not session:
            print("ERROR: Weather server session not available.")
            return

        client, message_url = session

        response = await client.get("http://localhost:8001/health", timeout=2.0)
        print(f"Health check: {response.status_code} - {response.text}")
        if response.status_code != 200:
            return

        tool_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "fetch_weather_data",
                "arguments": {"city": "London"},
            },
        }
        post_response = await client.post(message_url, json=tool_payload)
        print(f"Tool POST: {post_response.status_code} - {post_response.text}")

        tool_result = None
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            message = await wait_for_message("weather", timeout=2.0)
            if message and isinstance(message, dict) and message.get("id") == 2:
                tool_result = message
                break

        if tool_result:
            print(f"Tool result: {json.dumps(tool_result, indent=2)}")
        else:
            print("ERROR: Timed out waiting for tool result.")
    finally:
        await shutdown_all_servers()
        print("Test complete, cleanup done.")


if __name__ == "__main__":
    main()
