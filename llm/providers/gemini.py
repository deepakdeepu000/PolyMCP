import asyncio
import json
from typing import Any, Dict, List

from google import genai
from config.settings import GEMINI_API_KEY, GEMINI_MODEL


def _to_gemini_contents(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

    contents: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "tool":
            tool_name = msg.get("name")
            try:
                parsed = json.loads(content) if isinstance(content, str) else content
            except json.JSONDecodeError:
                parsed = {"content": content}

            contents.append({
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": tool_name,
                            "response": {"content": parsed},
                        }
                    }
                ],
            })
            continue

        gemini_role = "user" if role == "user" else "model"
        contents.append({"role": gemini_role, "parts": [{"text": content}]})

    return contents


def _to_gemini_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _strip_unsupported(schema: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        for key, value in schema.items():
            if key == "additionalProperties":
                continue
            if isinstance(value, dict):
                cleaned[key] = _strip_unsupported(value)
            elif isinstance(value, list):
                cleaned[key] = [
                    _strip_unsupported(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                cleaned[key] = value
        return cleaned

    declarations = []
    for tool in tools:
        fn = tool.get("function", {})
        declarations.append({
            "name": fn.get("name"),
            "description": fn.get("description"),
            "parameters": _strip_unsupported(fn.get("parameters") or {}),
        })
    return [{"function_declarations": declarations}] if declarations else []


async def _gemini_chat(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> dict:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set")

    payload = {
        "contents": _to_gemini_contents(messages),
        "tools": _to_gemini_tools(tools),
    }

    genai_client = genai.Client(api_key=GEMINI_API_KEY)

    response = await asyncio.to_thread(
        genai_client.models.generate_content,
        model=GEMINI_MODEL,
        contents=payload["contents"],
        config={"tools": payload["tools"]},
    )

    tool_calls = []
    text_parts = []

    if isinstance(response, dict):
        candidates = response.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        for part in parts:
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "name": fc.get("name"),
                    "arguments": fc.get("args", {}),
                    "id": None,
                })
            elif "text" in part:
                text_parts.append(part["text"])
    else:
        candidates = getattr(response, "candidates", []) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", []) if content else []
            for part in parts:
                function_call = getattr(part, "function_call", None)
                if function_call is not None:
                    tool_calls.append({
                        "name": getattr(function_call, "name", None),
                        "arguments": getattr(function_call, "args", {}) or {},
                        "id": getattr(function_call, "id", None),
                    })
                    continue

                text_value = getattr(part, "text", None)
                if text_value:
                    text_parts.append(text_value)

    if tool_calls:
        return {"content": None, "tool_calls": tool_calls}

    return {"content": "".join(text_parts).strip(), "tool_calls": []}
    