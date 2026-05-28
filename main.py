import uvicorn
import asyncio
import logging
import json
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

from llm.llm_client import LLMClient
from mcp_client import get_tool_schemas, run_tools_in_parallel
from utils.prompts import prompt_templets
from config.settings import MAX_TOOL_ROUNDS
from utils.logging_setup import configure_logging
from utils.tools.server_manager import startup_all_servers, shutdown_all_servers

configure_logging()

logger = logging.getLogger(__name__)
_LLM_RATE_LIMIT_SECONDS = 1.0
_llm_rate_lock = asyncio.Lock()
_last_llm_call_time: Optional[float] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Starting MCP servers...")
        startup_status = await startup_all_servers()
        failed = [name for name, ok in startup_status.items() if not ok]
        if failed:
            raise RuntimeError(f"Failed to start MCP servers: {', '.join(failed)}")
        logger.info("MCP servers started successfully.")
        yield
    finally:
        logger.info("Shutting down MCP servers...")
        await shutdown_all_servers()
        logger.info("MCP servers shut down successfully.")


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    query: str


@app.post("/chat")
async def chat(request: ChatRequest):
    global _last_llm_call_time
    query = request.query

    if not query:
        raise HTTPException(status_code=400, detail="Missing prompt / query / user_query")

    logger.info("Received query: %s", query)

    max_rounds = MAX_TOOL_ROUNDS or 5
    tools = get_tool_schemas()

    messages: list[dict[str, Any]] = [
        {
            "role":    "system",
            "content": prompt_templets.build_system_prompt(),
        },
        {
            "role":    "user",
            "content": prompt_templets.build_user_message(query),
        },
    ]

    for _ in range(max_rounds):
        async with _llm_rate_lock:
            if _last_llm_call_time is not None:
                elapsed = asyncio.get_running_loop().time() - _last_llm_call_time
                if elapsed < _LLM_RATE_LIMIT_SECONDS:
                    await asyncio.sleep(_LLM_RATE_LIMIT_SECONDS - elapsed)
        logger.info(f"LLM call with messages [main.py]: {json.dumps(messages, indent=2)}")
        llm_response = await LLMClient(messages, tools)
        async with _llm_rate_lock:
            _last_llm_call_time = asyncio.get_running_loop().time()
        tool_calls: list[dict[str, Any]] = llm_response.get("tool_calls") or []
        content: Optional[str] = llm_response.get("content")
        
        logger.debug("LLM tool calls: %s", json.dumps(tool_calls, indent=2))

        if not tool_calls:
            # Model produced a final text answer — done.
            final = content or ""
            messages.append({"role": "assistant", "content": final})
            return {"answer": final}

        # 1. Record the assistant's decision to call tools.
        #    Required by most LLM APIs to keep conversation history valid.
        messages.append({
            "role":    "assistant",
            "content": content or "",
            "tool_calls": [
                {
                    "id":   tc.get("id") or tc["name"],
                    "type": "function",
                    "function": {
                        "name":      tc["name"],
                        "arguments": json.dumps(tc.get("arguments") or {}),
                    },
                }
                for tc in tool_calls
            ],
        })

        # 2. Run all tool calls concurrently.
        tool_results = await run_tools_in_parallel(tool_calls)
        logger.debug("Tool results: %s", json.dumps(tool_results, indent=2))

        # 3. Append each result as a tool message.
        for result in tool_results:
            messages.append({
                "role":         "tool",
                "name":         result["name"],
                "tool_call_id": result.get("id") or result["name"],
                "content":      json.dumps(result["output"], ensure_ascii=False),
            })

        # 4. Nudge the model to synthesise results rather than call more tools.
        #    Especially helpful for local LLMs with weaker instruction following.
        messages.append({
            "role":    "user",
            "content": "You now have all the tool results above. Please give the final answer.",
        })

    raise HTTPException(
        status_code=500,
        detail=f"Agent did not produce a final answer within {max_rounds} rounds.",
    )


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=8000)
