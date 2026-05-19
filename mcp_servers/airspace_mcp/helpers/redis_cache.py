import json
import logging
from typing import Any

from .redis_client.client import get_redis_client

logger = logging.getLogger(__name__)


async def get_cache(key: str) -> Any:
    """Fetch a JSON-serialised value from Redis. Returns {} on miss or error."""
    try:
        client = await get_redis_client()
        cached_data = await client.get(key)
        if cached_data:
            return json.loads(cached_data)
        return {}
    except Exception:
        logger.exception("get_cache failed for key '%s'", key)
        return {}


async def set_cache(key: str, value: Any) -> None:
    """Store a value as JSON in Redis."""
    try:
        client = await get_redis_client()
        await client.set(key, json.dumps(value))
    except Exception:
        logger.exception("set_cache failed for key '%s'", key)


async def set_ttl_cache(key: str, value: Any, ttl_seconds: int) -> None:
    """Store a value as JSON in Redis with a TTL."""
    try:
        client = await get_redis_client()
        await client.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        logger.exception("set_ttl_cache failed for key '%s'", key)


async def delete_cache(key: str) -> None:
    """Delete a key from Redis."""
    try:
        client = await get_redis_client()
        await client.delete(key)
    except Exception:
        logger.exception("delete_cache failed for key '%s'", key)


async def clear_cache(pattern: str) -> None:
    """Delete all keys matching a glob pattern from Redis."""
    try:
        client = await get_redis_client()
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)
    except Exception:
        logger.exception("clear_cache failed for pattern '%s'", pattern)
