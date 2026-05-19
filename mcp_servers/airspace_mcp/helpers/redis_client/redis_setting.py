from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class RedisSettings(BaseSettings):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

@lru_cache()
def get_redis_settings() -> RedisSettings:
    return RedisSettings()