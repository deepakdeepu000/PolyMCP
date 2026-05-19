import json
import asyncio
import time
from typing import Any, Dict, List

import httpx
from config.settings import OPENAI_API_KEY, OPENAI_MODEL


_OPENAI_MIN_REQUEST_INTERVAL = 1.0
_openai_rate_lock = asyncio.Lock()
_openai_last_request_at = 0.0


async def _apply_openai_rate_limit() -> None:
	global _openai_last_request_at

	async with _openai_rate_lock:
		now = time.monotonic()
		elapsed = now - _openai_last_request_at
		if elapsed < _OPENAI_MIN_REQUEST_INTERVAL:
			await asyncio.sleep(_OPENAI_MIN_REQUEST_INTERVAL - elapsed)
		_openai_last_request_at = time.monotonic()


async def _openai_chat(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> dict:
	if not OPENAI_API_KEY:
		raise ValueError("OPENAI_API_KEY is not set")

	url = "https://api.openai.com/v1/chat/completions"
	headers = {
		"Authorization": f"Bearer {OPENAI_API_KEY}",
		"Content-Type": "application/json",
	}

	payload = {
		"model": OPENAI_MODEL,
		"messages": messages,
		"tools": tools,
		"tool_choice": "auto",
	}

	await _apply_openai_rate_limit()

	async with httpx.AsyncClient(timeout=120) as client:
		response = await client.post(url, json=payload, headers=headers)
		response.raise_for_status()
		data = response.json()

	choice = data["choices"][0]["message"]
	tool_calls = []

	for tc in choice.get("tool_calls", []) or []:
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

	return {"content": choice.get("content", ""), "tool_calls": []}
