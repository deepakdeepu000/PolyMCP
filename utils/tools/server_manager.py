import asyncio
import httpx
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from config.settings import MCP_SERVER_START_TIMEOUT_SECONDS
from utils.tools.tool_registry import MCP_SERVER_URLS, get_server_start_command


logger = logging.getLogger(__name__)


@dataclass
class ServerState:
    process: Optional[subprocess.Popen] = None
    stderr_task: Optional[asyncio.Task] = None
    started_by_manager: bool = False
    start_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ── Session (established once after startup) ──────────────────────────
    is_ready: bool = False
    message_url: Optional[str] = None       # e.g. http://localhost:8001/messages/?session_id=xxx
    sse_task: Optional[asyncio.Task] = None # keeps SSE stream alive
    sse_response: Optional[httpx.Response] = None
    http_client: Optional[httpx.AsyncClient] = None
    message_queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class MCPServerManager:
    def __init__(self) -> None:
        self._states: Dict[str, ServerState] = {}
        self._logger = logging.getLogger(__name__)

    # ── Public API ────────────────────────────────────────────────────────

    async def startup_all(self) -> Dict[str, bool]:
        """Start every registered server and handshake. Call once at app boot."""
        results = await asyncio.gather(
            *[self._start_server(key) for key in MCP_SERVER_URLS],
            return_exceptions=True,
        )
        status = {}
        for key, result in zip(MCP_SERVER_URLS, results):
            if isinstance(result, Exception):
                self._logger.error("Error starting '%s': %s", key, result)
                status[key] = False
            else:
                status[key] = result
        self._logger.info("MCP startup complete: %s", status)
        return status

    def get_session(self, server_key: str) -> Optional[tuple[httpx.AsyncClient, str]]:
        """
        Returns (client, message_url) for a ready server.
        Tool executor calls this — no handshake, just POST.
        """
        state = self._states.get(server_key)
        if state and state.is_ready and state.http_client and state.message_url:
            return state.http_client, state.message_url
        return None

    async def shutdown_all(self) -> None:
        """Tear down all sessions and processes. Call once at app shutdown."""
        await asyncio.gather(
            *[self._shutdown_server(k, s) for k, s in self._states.items()],
            return_exceptions=True,
        )
        self._logger.info("All MCP servers shut down.")

    # ── Startup internals ─────────────────────────────────────────────────

    async def _start_server(self, server_key: str) -> bool:
        url = MCP_SERVER_URLS[server_key]
        state = self._states.setdefault(server_key, ServerState())

        async with state.start_lock:
            # Launch process if not externally managed
            if not await self._is_alive(url):
                command = get_server_start_command(server_key)
                if not command:
                    self._logger.warning("No start command for '%s'", server_key)
                    return False
                try:
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                except Exception:
                    self._logger.exception("Failed to launch '%s'", server_key)
                    return False

                state.process = process
                state.started_by_manager = True

                if process.stderr:
                    state.stderr_task = asyncio.create_task(
                        asyncio.to_thread(self._stream_stderr_sync, server_key, process.stderr)
                    )

            # Wait for /health (2 checks total, spread across timeout)
            delay = max(MCP_SERVER_START_TIMEOUT_SECONDS / 2, 0.2)
            is_alive = False
            for attempt in range(2):
                is_alive = await self._is_alive(url)
                if is_alive:
                    break
                if attempt == 0:
                    await asyncio.sleep(delay)
            if not is_alive:
                self._logger.error("'%s' did not become healthy in time", server_key)
                return False

        # Handshake outside the lock (non-blocking for other servers)
        return await self._handshake(server_key, url, state)

    async def _handshake(self, server_key: str, base_url: str, state: ServerState) -> bool:
        """
        Open a persistent SSE connection, run initialize, mark session ready.
        After this, tool calls just POST to state.message_url.
        """
        client = httpx.AsyncClient(timeout=30.0)
        state.http_client = client

        # ── Step 1: open SSE stream, read the session endpoint ────────────
        message_url_future: asyncio.Future[Optional[str]] = asyncio.get_event_loop().create_future()

        async def _sse_reader():
            try:
                async with client.stream("GET", f"{base_url}/sse") as sse:
                    state.sse_response = sse
                    current_event = None
                    async for line in sse.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("event: "):
                            current_event = line[7:].strip()
                        elif line.startswith("data: "):
                            data = line[6:].strip()
                            if current_event == "endpoint" and not message_url_future.done():
                                # e.g. /messages/?session_id=abc123
                                full_url = f"{base_url}{data}" if data.startswith("/") else data
                                message_url_future.set_result(full_url)
                            elif current_event == "message":
                                try:
                                    message = json.loads(data)
                                except json.JSONDecodeError:
                                    message = {"raw": data}
                                await state.message_queue.put(message)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._logger.error("SSE reader for '%s' died: %s", server_key, exc)
                if not message_url_future.done():
                    message_url_future.set_result(None)

        state.sse_task = asyncio.create_task(_sse_reader())

        # Wait for endpoint to arrive (up to 10s)
        try:
            message_url = await asyncio.wait_for(
                asyncio.shield(message_url_future), timeout=10.0
            )
        except asyncio.TimeoutError:
            self._logger.error("'%s' SSE never sent endpoint", server_key)
            return False

        if not message_url:
            return False

        state.message_url = message_url
        self._logger.debug("'%s' SSE endpoint: %s", server_key, message_url)

        # ── Step 2: initialize ────────────────────────────────────────────
        try:
            init_resp = await client.post(message_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "agent", "version": "1.0.0"},
                },
            })
            init_resp.raise_for_status()
        except Exception:
            self._logger.exception("'%s' initialize failed", server_key)
            return False

        # ── Step 3: notifications/initialized ─────────────────────────────
        try:
            await client.post(message_url, json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": None,
            })
        except Exception:
            self._logger.exception("'%s' initialized notification failed", server_key)
            return False

        state.is_ready = True
        self._logger.info("'%s' session ready — tools can now be called.", server_key)
        return True

    # ── Shutdown internals ────────────────────────────────────────────────

    async def _shutdown_server(self, server_key: str, state: ServerState) -> None:
        state.is_ready = False

        if state.sse_task and not state.sse_task.done():
            state.sse_task.cancel()
            try:
                await state.sse_task
            except asyncio.CancelledError:
                pass

        if state.http_client:
            await state.http_client.aclose()
            state.http_client = None

        if state.process and state.process.poll() is None:
            state.process.terminate()
            try:
                await asyncio.to_thread(state.process.wait, timeout=5.0)
            except subprocess.TimeoutExpired:
                state.process.kill()
                await asyncio.to_thread(state.process.wait)

        if state.stderr_task and not state.stderr_task.done():
            state.stderr_task.cancel()
            try:
                await state.stderr_task
            except asyncio.CancelledError:
                pass

        state.process = None
        state.started_by_manager = False

    async def _is_alive(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                r = await client.get(f"{url.rstrip('/')}/health")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def _stream_stderr_sync(self, server_key: str, stream) -> None:
        for line in stream:
            text = str(line).strip()
            if not text:
                continue
            # Drop noisy INFO startup lines from uvicorn; keep warnings/errors.
            if text.startswith("INFO:"):
                continue
            if text.startswith("WARNING:") or text.startswith("WARN:"):
                self._logger.warning("MCP '%s' stderr: %s", server_key, text)
                continue
            if text.startswith("ERROR:") or text.startswith("CRITICAL:"):
                self._logger.error("MCP '%s' stderr: %s", server_key, text)
                continue
            self._logger.debug("MCP '%s' stderr: %s", server_key, text)


# ── Module-level singleton ────────────────────────────────────────────────────
_MANAGER = MCPServerManager()

async def startup_all_servers() -> Dict[str, bool]:
    return await _MANAGER.startup_all()

async def shutdown_all_servers() -> None:
    await _MANAGER.shutdown_all()

def get_session(server_key: str) -> Optional[tuple[httpx.AsyncClient, str]]:
    return _MANAGER.get_session(server_key)

async def wait_for_message(server_key: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    state = _MANAGER._states.get(server_key)
    if not state:
        return None
    try:
        return await asyncio.wait_for(state.message_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None

async def ensure_server(server_key: str) -> bool:
    is_started = await _MANAGER._start_server(server_key)
    logger.info("ensure_server('%s') -> %s", server_key, is_started)
    return is_started