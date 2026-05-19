import asyncio
from collections import defaultdict

from utils.logging_setup import configure_logging
from utils.tools.server_manager import ensure_server, shutdown_all_servers
from utils.tools.tool_registry import MCP_SERVER_URLS, get_tool_definitions


async def main() -> None:
    configure_logging()

    try:
        tools_by_server = defaultdict(list)
        for tool in get_tool_definitions():
            server_key = tool.get("server")
            if server_key:
                tools_by_server[server_key].append(tool["name"])

        for server_key in sorted(tools_by_server.keys()):
            started = await ensure_server(server_key)
            base_url = MCP_SERVER_URLS.get(server_key, "")
            print(f"\nServer: {server_key}")
            print(f"Status: {'started' if started else 'not available'}")
            print(f"Base URL: {base_url}")
            if base_url:
                print(f"SSE endpoint: {base_url}/sse")
                print(f"Messages endpoint: {base_url}/messages/")
            print("Tools:")
            for name in tools_by_server[server_key]:
                print(f"  - {name}")
    finally:
        await shutdown_all_servers()


if __name__ == "__main__":
    asyncio.run(main())
