import asyncio
from asyncio import tasks
import logging
import time
from typing import Any

from utils.tools.tool_registry import get_tool_definition, get_tool_schemas
from utils.tools.server_manager import get_session, wait_for_message


logger = logging.getLogger(__name__)

import asyncio
import time
from typing import Any, List, Dict

async def call_mcp_tool(
    message_url: str,
    tool_name: str,
    arguments: dict,
    call_id: Any = 2,
    *,
    client,
) -> dict:
    """POST a tool/call request and return a normalised result dict."""
    import httpx
    try:
        response = await client.post(
            message_url, 
            json={
                "jsonrpc": "2.0",
                "id": call_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
        )
        response.raise_for_status()
        return {"ok": True, "data": response.json()}
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"HTTP {exc.response.status_code}", "details": exc.response.text}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Tool request timed out"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def run_tools_in_parallel(tool_calls: List[Dict]) -> List[Dict]:
    """Execute all tool calls concurrently and return a list of result dicts."""

    async def _error(tool_name: str, call_id: Any, message: str) -> dict:
        return {"name": tool_name, "id": call_id, "output": {"ok": False, "error": message}}
    
    async def _wait_for_result(tool_name: str, call_id: Any, server_key: str) -> dict:
        """Helper to poll/wait for SSE or long-poll message responses."""
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            # Assuming wait_for_message is defined globally elsewhere
            message = await wait_for_message(server_key, timeout=2.0)
            if message and isinstance(message, dict) and message.get("id") == call_id:
                return {"name": tool_name, "id": call_id, "output": {"ok": True, "data": message}}
        return await _error(tool_name, call_id, "Tool result timeout")

    async def _process_single_tool(call: dict) -> dict:
        """Handles the async pipeline for one tool so they run truly in parallel."""
        tool_name = call.get("name")
        call_id   = call.get("id") or 2
        arguments = call.get("arguments") or {}

        # 1. Validation
        tool_def = get_tool_definition(tool_name) if tool_name else None
        if not tool_def:
            return await _error(tool_name, call_id, "Unknown tool")

        server_key = tool_def.get("server")
        session = get_session(server_key) if server_key else None
        if not session:
            return await _error(tool_name, call_id, "Server not ready or unknown")

        client, message_url = session
        
        # 2. Trigger the tool call (POST)
        tool_payload = {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        
        try:
            post_response = await client.post(message_url, json=tool_payload)
            if post_response.status_code >= 400:
                return await _error(tool_name, call_id, f"Tool post failed: {post_response.status_code}")
        except Exception as e:
            return await _error(tool_name, call_id, f"Tool post error: {str(e)}")
        
        # 3. Wait for asynchronous background result
        return await _wait_for_result(tool_name, call_id, server_key)

    # Wrap every tool call into a coroutine and execute them concurrently via gather
    tasks = [_process_single_tool(call) for call in tool_calls]
    return await asyncio.gather(*tasks)