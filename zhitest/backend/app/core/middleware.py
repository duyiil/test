from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.request_context import request_id_var

logger = logging.getLogger("zhitest.access")
_RID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


def _cookie(name: str, value: str, max_age: int, secure: bool) -> bytes:
    parts = [f"{name}={value}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts).encode("ascii")


class RequestContextMiddleware:
    """生成 requestId，并在成功响应上刷新 HttpOnly 会话 Cookie。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        incoming = headers.get("x-request-id", "")
        rid = incoming if _RID_RE.fullmatch(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["request_id"] = rid
        status_code = 500
        started = time.perf_counter()
        settings = get_settings()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                raw = list(message.get("headers") or [])
                raw.append((b"x-request-id", rid.encode("ascii")))
                state: dict[str, Any] = scope.get("state") or {}
                if state.get("clear_session_cookie"):
                    raw.append(
                        (
                            b"set-cookie",
                            _cookie(settings.session_cookie_name, "", 0, settings.cookie_secure),
                        )
                    )
                elif status_code < 400 and state.get("refreshed_session_token"):
                    raw.append(
                        (
                            b"set-cookie",
                            _cookie(
                                settings.session_cookie_name,
                                str(state["refreshed_session_token"]),
                                settings.session_ttl_seconds,
                                settings.cookie_secure,
                            ),
                        )
                    )
                message["headers"] = raw
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %s %.1fms",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status_code,
                elapsed_ms,
            )
            request_id_var.reset(token)
