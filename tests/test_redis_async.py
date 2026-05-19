"""
Smoke test: verifies the Redis connection is live and basic set/get works.
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config.settings import get_settings


async def main() -> None:
    from redis import asyncio as aioredis

    url = get_settings().get_redis_url()
    client = aioredis.from_url(url, decode_responses=True)

    try:
        pong = await client.ping()
        print(f"PING: {pong}")

        await client.set("mcp:test:async", "ok", ex=30)
        value = await client.get("mcp:test:async")
        print(f"GET mcp:test:async: {value}")

        dbsize = await client.dbsize()
        print(f"DBSIZE: {dbsize}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
