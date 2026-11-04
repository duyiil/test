from __future__ import annotations

import json
from typing import Any

from starlette.responses import JSONResponse

from app.core.request_context import get_request_id


class UTF8JSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def success(data: Any, message: str = "操作成功") -> dict[str, Any]:
    return {
        "code": "SUCCESS",
        "message": message,
        "details": None,
        "requestId": get_request_id(),
        "data": data,
    }


def error_body(code: str, message: str, details: Any = None, request_id: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details,
        "requestId": get_request_id() if request_id is None else request_id,
    }
