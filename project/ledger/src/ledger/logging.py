"""结构化日志：JSON formatter、request_id 全链路与访问日志中间件。"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    """将 LogRecord 序列化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict):
            payload.update(extra_data)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str) -> None:
    """为 root logger 配置 stderr JSON handler（幂等）。"""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler) and isinstance(
            handler.formatter, JsonFormatter
        ):
            break
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)

    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.propagate = True


def get_logger(name: str) -> logging.Logger:
    """返回 ledger 命名空间下的 logger。"""
    return logging.getLogger(f"ledger.{name}")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """注入 request_id，记录访问日志并回写响应头；兜底未处理异常为 500。"""

    async def dispatch(self, request: Request, call_next):
        from fastapi.responses import JSONResponse
        from starlette.exceptions import HTTPException

        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        request_id_ctx.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except HTTPException:
            # 保持 HTTPException 的默认处理（状态码/detail 不变）
            raise
        except Exception as exc:
            get_logger("app").error(
                "unhandled_exception",
                extra={"extra_data": {"path": request.url.path, "error": repr(exc)}},
            )
            response = JSONResponse(
                status_code=500,
                content={"detail": "服务器内部错误", "request_id": request_id},
            )
            status_code = 500
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-Id"] = request_id
        get_logger("http").info(
            "request",
            extra={
                "extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        return response
