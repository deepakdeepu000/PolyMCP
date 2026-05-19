from redis import asyncio as aioredis
from helpers.redis_client.redis_setting import get_redis_settings

redis_settings = get_redis_settings()

# Initialize the Redis client
redis_client: aioredis.Redis | None = None

async def get_redis_client() -> aioredis.Redis:
    """
    Return the shared async Redis client.
    Initialises lazily on first call so the event loop is already running.
    """
    global redis_client
    if redis_client is None:
        url = get_redis_settings().get_redis_url()
        redis_client = aioredis.from_url(url, decode_responses=True)
    return redis_client