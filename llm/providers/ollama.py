import json
import httpx
from config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL

_OLLAMA_SYSTEM_PROMPT = """\
You are a helpful assistant with access to tools.

RULES:
- If required arguments are missing, ALWAYS ask the user before calling any tool.
- Never guess or invent argument values.
- If multiple tools are independent of each other, call them all at once in a single response.
- If tool B depends on the result of tool A, call A first, wait for result, then call B.
- Once you have all tool results, give a final answer. Do not call tools again unnecessarily.
"""


async def _ollama_chat(messages: list, tools: list) -> dict:
    url = f"{OLLAMA_BASE_URL}/api/chat"

    # Prepend the Ollama-specific system prompt without mutating the caller's list.
    augmented_messages = [
        {"role": "system", "content": _OLLAMA_SYSTEM_PROMPT},
        *messages,
    ]

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            url,
            json={
                "model": OLLAMA_MODEL,
                "messages": augmented_messages,
                "tools": tools,
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()

    msg = data.get("message", {})
    tool_calls = []

    for tc in msg.get("tool_calls", []) or []:
        fn = tc.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            args = json.loads(args)
        tool_calls.append({
            "name": fn.get("name"),
            "arguments": args,
            "id": tc.get("id"),
        })

    if tool_calls:
        return {"content": None, "tool_calls": tool_calls}

    return {"content": msg.get("content", ""), "tool_calls": []}
