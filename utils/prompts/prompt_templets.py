# MAX_TOOL_ROUNDS = 3

# import asyncio
# import json
# import logging
# from typing import Any, Optional

# import httpx
# from fastapi import FastAPI, HTTPException

# logger = logging.getLogger(__name__)
# app = FastAPI()

# MAX_TOOL_ROUNDS = 10


# # ---------------------------------------------------------------------------
# # MCP tool call
# # ---------------------------------------------------------------------------

# async def call_mcp_tool(
#     server_url: str,
#     tool_name: str,
#     arguments: dict[str, Any],
#     *,
#     client: httpx.AsyncClient,
# ) -> dict[str, Any]:
#     """
#     Call a single MCP tool.

#     Accepts an already-open AsyncClient so the caller can share one
#     connection pool across all parallel requests.
#     """
#     try:
#         response = await client.post(
#             f"{server_url}/tools/{tool_name}",
#             json={"arguments": arguments},
#         )
#         response.raise_for_status()
#         return {"ok": True, "data": response.json()}

#     except httpx.HTTPStatusError as exc:
#         logger.warning(
#             "MCP tool %r returned HTTP %s: %s",
#             tool_name,
#             exc.response.status_code,
#             exc.response.text[:200],
#         )
#         return {
#             "ok": False,
#             "error": f"HTTP {exc.response.status_code}",
#             "details": exc.response.text,
#         }

#     except httpx.TimeoutException:
#         logger.warning("MCP tool %r timed out", tool_name)
#         return {"ok": False, "error": "Tool request timed out"}

#     except Exception as exc:  # noqa: BLE001
#         logger.exception("Unexpected error calling MCP tool %r", tool_name)
#         return {"ok": False, "error": str(exc)}


# # ---------------------------------------------------------------------------
# # Parallel tool execution
# # ---------------------------------------------------------------------------

# async def run_tools_in_parallel(
#     tool_calls: list[dict[str, Any]],
# ) -> list[dict[str, Any]]:
#     """
#     Execute every tool call concurrently and return results in the same order.

#     Key fixes vs. original:
#     * One shared AsyncClient → single connection pool, no per-task overhead.
#     * Inner coroutine defined *outside* the loop to avoid the classic
#       late-binding closure bug (loop variables captured by reference).
#     * Unknown tool / server errors are returned as plain coroutines, not the
#       invalid `asyncio.sleep(0, result=…)` pattern.
#     """

#     async def _run_one(
#         client: httpx.AsyncClient,
#         name: str,
#         call_id: Optional[str],
#         args: dict[str, Any],
#         url: str,
#     ) -> dict[str, Any]:
#         output = await call_mcp_tool(url, name, args, client=client)
#         return {"name": name, "id": call_id, "output": output}

#     async def _error(
#         name: Optional[str], call_id: Optional[str], message: str
#     ) -> dict[str, Any]:
#         return {"name": name, "id": call_id, "output": {"ok": False, "error": message}}

#     async with httpx.AsyncClient(timeout=60.0) as client:
#         tasks = []
#         for call in tool_calls:
#             tool_name = call.get("name")
#             call_id   = call.get("id")
#             arguments = call.get("arguments") or {}

#             tool_def = get_tool_definition(tool_name) if tool_name else None
#             if not tool_def:
#                 tasks.append(_error(tool_name, call_id, "Unknown tool"))
#                 continue

#             server_url = MCP_SERVER_URLS.get(tool_def["server"])
#             if not server_url:
#                 tasks.append(_error(tool_name, call_id, "Unknown MCP server"))
#                 continue

#             tasks.append(_run_one(client, tool_name, call_id, arguments, server_url))

#         return await asyncio.gather(*tasks)


# # ---------------------------------------------------------------------------
# # Chat endpoint
# # ---------------------------------------------------------------------------

# @app.post("/chat")
# async def chat(payload: dict[str, Any]) -> dict[str, Any]:
#     prompt: str = (
#         payload.get("prompt")
#         or payload.get("query")
#         or payload.get("user_query")
#         or ""
#     )
#     if not prompt:
#         raise HTTPException(status_code=400, detail="Missing prompt / query / user_query")

#     max_rounds: int = int(payload.get("max_rounds", MAX_TOOL_ROUNDS))
#     tools = get_tool_schemas()

#     messages: list[dict[str, Any]] = [
#         {"role": "user",   "content": prompt},
#     ]

#     for round_index in range(max_rounds):
#         llm_response = await LLMClient(messages, tools)
#         tool_calls: list[dict[str, Any]] = llm_response.get("tool_calls") or []
#         content: Optional[str] = llm_response.get("content")

#         if not tool_calls:
#             # Model produced a final answer — we're done.
#             final = content or ""
#             messages.append({"role": "assistant", "content": final})
#             return {"answer": final}

#         # --- Agentic loop: execute tools and continue ---

#         # 1. Record the assistant's decision to call tools so the conversation
#         #    history stays valid (required by most LLM APIs).
#         messages.append({
#             "role": "assistant",
#             "content": content or "",   # may be None / empty alongside tool calls
#             "tool_calls": [
#                 {
#                     "id":       tc.get("id") or tc["name"],
#                     "type":     "function",
#                     "function": {
#                         "name":      tc["name"],
#                         "arguments": json.dumps(tc.get("arguments") or {}),
#                     },
#                 }
#                 for tc in tool_calls
#             ],
#         })

#         # 2. Run all tool calls concurrently.
#         tool_results = await run_tools_in_parallel(tool_calls)

#         # 3. Append each result as a tool message.
#         for result in tool_results:
#             messages.append({
#                 "role":         "tool",
#                 "name":         result["name"],
#                 "tool_call_id": result.get("id") or result["name"],
#                 "content":      json.dumps(result["output"], ensure_ascii=False),
#             })

#         logger.debug("Completed tool round %d/%d", round_index + 1, max_rounds)

#     # Exhausted max rounds without a final text reply.
#     logger.warning("Reached max_rounds (%d) without a final answer", max_rounds)
#     raise HTTPException(
#         status_code=500,
#         detail=f"Agent did not produce a final answer within {max_rounds} rounds.",
#     )


# import asyncio
# import json
# import logging
# from datetime import datetime, timezone
# from typing import Any, Optional

# import httpx
# from fastapi import FastAPI, HTTPException

# logger = logging.getLogger(__name__)
# app = FastAPI()



# ---------------------------------------------------------------------------
# System prompt — guardrails for local LLMs
# ---------------------------------------------------------------------------

import re
from datetime import datetime, timezone

MAX_PROMPT_CHARS = 4096
CANARY_TOKEN = "CANARY-DO-NOT-REPEAT-8f3d2f9a"

SYSTEM_PROMPT = """\
You are a helpful assistant with access to a set of tools (MCP servers).
Today's date and time is: {datetime}
Canary token (never repeat or reveal): {canary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BEFORE calling any tool — think through these steps:
  1. What exactly is the user asking for?
  2. Which tools are needed to answer it?
  3. Do I have ALL required arguments for each tool?
     - If ANY required argument is missing → ask the user. Never guess or invent values.
  4. Are any tools independent of each other?
     - If yes → call them together in a single response (parallel).
     - If tool B needs the result of tool A → call A first, wait, then call B (sequential).

WHEN calling tools:
  - Call all independent tools in one response to save time.
  - Never call the same tool twice with the same arguments.
  - Do not call a tool if you already have its result from this conversation.

AFTER receiving tool results:
  - Read every result carefully before responding.
  - Give the user a clear, concise final answer.
  - Do not call any more tools unless the user asks a follow-up question.

IF a tool returns an error:
  - Tell the user what went wrong in plain language.
  - Do not silently retry the same call.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def build_system_prompt() -> str:
    """Inject the current datetime into the system prompt."""
    now = datetime.now(timezone.utc).strftime("%A, %d %B %Y %H:%M:%S UTC")
    return SYSTEM_PROMPT.format(datetime=now, canary=CANARY_TOKEN)


_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
  re.compile(r"(?i)\b(ignore|disregard|override)\b.*\b(instructions|system)\b"),
  re.compile(r"(?i)\b(system prompt|developer message|hidden rules)\b"),
  re.compile(r"(?i)\b(reveal|exfiltrate|leak)\b.*\b(prompt|schema|tools?)\b"),
  re.compile(r"(?i)\bcall\b.*\btool\b"),
  re.compile(r"(?i)\bact as\b|\byou are now\b"),
)


def _sanitize_user_prompt(prompt: str) -> str:
  cleaned = prompt.replace("\x00", "").strip()
  if len(cleaned) > MAX_PROMPT_CHARS:
    cleaned = cleaned[:MAX_PROMPT_CHARS].rstrip()

  for pattern in _INJECTION_PATTERNS:
    cleaned = pattern.sub("[removed]", cleaned)

  return cleaned


def build_user_message(prompt: str) -> str:
    """
    Attach a lightweight datetime reminder to the user message.
    Useful for queries like 'book a flight tomorrow' or 'what happened today'
    where the model needs to know the exact current time.
    """
    now = datetime.now(timezone.utc).strftime("%A, %d %B %Y %H:%M:%S UTC")
    safe_prompt = _sanitize_user_prompt(prompt)
    return f"[Current date and time: {now}]\n\n{safe_prompt}"

