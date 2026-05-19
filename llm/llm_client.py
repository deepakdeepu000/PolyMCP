import logging

from httpx import HTTPStatusError, RequestError, ReadTimeout

from config.settings import LLM_PROVIDER
from llm.providers.openai import _openai_chat
from llm.providers.gemini import _gemini_chat
from llm.providers.ollama import _ollama_chat

logger = logging.getLogger(__name__)


async def LLMClient(messages: list, tools: list) -> dict:
    """
    Universal chat function. Routes to the correct LLM based on LLM_PROVIDER in .env.

    Returns:
        {
            "content": "text reply OR None if tool call",
            "tool_calls": [ { "name": ..., "arguments": {...}, "id": "..." } ] or []
        }
    """
    providers = {
        "openai": _openai_chat,
        "gemini": _gemini_chat,
        "ollama": _ollama_chat,
    }

    if LLM_PROVIDER not in providers:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{LLM_PROVIDER}'. "
            f"Set it to openai, gemini, or ollama in .env"
        )

    ordered_providers = [LLM_PROVIDER] + [p for p in providers if p != LLM_PROVIDER]
    last_error = None

    for provider_name in ordered_providers:
        try:
            logger.info("Trying LLM provider: %s", provider_name)
            return await providers[provider_name](messages, tools)
        except (HTTPStatusError, RequestError, ReadTimeout, TimeoutError, ValueError) as exc:
            last_error = exc
            logger.warning("Provider '%s' failed: %s", provider_name, exc)
            continue

    raise ValueError(f"LLM request failed for all providers. Last error: {last_error}")
