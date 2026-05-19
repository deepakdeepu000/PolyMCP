from functools import lru_cache
from typing import Optional
from pydantic import SecretStr, Field, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM ──────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "gemini"

    OPENAI_API_KEY: SecretStr = SecretStr("")
    OPENAI_MODEL: str = "gpt-5.4-mini"

    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL: str = "gemini-3-flash-preview"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # ── External APIs ─────────────────────────────────────────────────────
    WEATHERAPI_KEY: SecretStr = SecretStr("")
    AERODATABOX_API_KEY: SecretStr = SecretStr("")

    # ── MCP server base URLs ──────────────────────────────────────────────
    WEATHER_MCP_URL: str = ""
    FLIGHTS_MCP_URL: str = ""

    # ── Redis ─────────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ── Agent ─────────────────────────────────────────────────────────────
    MAX_TOOL_ROUNDS: int = 5

    # ── MCP server lifecycle ──────────────────────────────────────────────
    MCP_SERVER_IDLE_TTL_SECONDS: int = 300
    MCP_SERVER_START_TIMEOUT_SECONDS: int = 10

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# ── Module-level constants (safe to import directly) ─────────────────────────
_s = get_settings()

LLM_PROVIDER: str = _s.LLM_PROVIDER

OPENAI_API_KEY: str = _s.OPENAI_API_KEY.get_secret_value()
OPENAI_MODEL: str = _s.OPENAI_MODEL

GEMINI_API_KEY: str = _s.GEMINI_API_KEY.get_secret_value()
GEMINI_MODEL: str = _s.GEMINI_MODEL

OLLAMA_BASE_URL: str = _s.OLLAMA_BASE_URL
OLLAMA_MODEL: str = _s.OLLAMA_MODEL

WEATHERAPI_KEY: str = _s.WEATHERAPI_KEY.get_secret_value()
AERODATABOX_API_KEY: str = _s.AERODATABOX_API_KEY.get_secret_value()

WEATHER_MCP_URL: str = _s.WEATHER_MCP_URL
FLIGHTS_MCP_URL: str = _s.FLIGHTS_MCP_URL

REDIS_HOST: str = _s.REDIS_HOST
REDIS_PORT: int = _s.REDIS_PORT
REDIS_DB: int = _s.REDIS_DB

MAX_TOOL_ROUNDS: int = _s.MAX_TOOL_ROUNDS

MCP_SERVER_IDLE_TTL_SECONDS: int = _s.MCP_SERVER_IDLE_TTL_SECONDS
MCP_SERVER_START_TIMEOUT_SECONDS: int = _s.MCP_SERVER_START_TIMEOUT_SECONDS