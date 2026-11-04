from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.core.middleware import AuthGateMiddleware, RequestContextMiddleware
from app.core.request_context import request_id_from
from app.core.responses import UTF8JSONResponse, error_body
from app.modules.bootstrap import bootstrap_admin

logger = logging.getLogger("zhitest")

_STATUS_CODE = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


def _validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for err in exc.errors():
        details.append(
            {
                "loc": ".".join(str(part) for part in err.get("loc", [])),
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
        )
    return details


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> UTF8JSONResponse:
        return UTF8JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details, request_id_from(_request)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> UTF8JSONResponse:
        return UTF8JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", "参数校验失败", _validation_details(exc), request_id_from(_request)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_request: Request, exc: StarletteHTTPException) -> UTF8JSONResponse:
        code = _STATUS_CODE.get(exc.status_code, "HTTP_ERROR")
        message = "资源不存在" if exc.status_code == 404 else str(exc.detail)
        return UTF8JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, message, request_id=request_id_from(_request)),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> UTF8JSONResponse:
        logger.exception("unhandled error")
        return UTF8JSONResponse(
            status_code=500,
            content=error_body("INTERNAL_ERROR", "服务器内部错误", request_id=request_id_from(_request)),
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.auto_bootstrap:
        bootstrap_admin(settings)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title=settings.app_name, lifespan=lifespan, default_response_class=UTF8JSONResponse)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
