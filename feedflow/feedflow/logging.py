"""JSON 结构化日志模块：基于标准库 logging，每行输出一条 JSON 到 stdout。

提供 request_id 上下文（contextvars）以便在同一次请求内串联日志。
"""

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

# 请求级上下文：保存当前 request_id
_request_id_var: contextvars.ContextVar = contextvars.ContextVar(
    "feedflow_request_id", default=None
)

# 标记 handler 是否已安装，避免重复添加
_HANDLER_FLAG = "_feedflow_json_handler"


def set_request_id(value):
    """设置当前上下文的 request_id，返回 token 便于恢复。"""
    return _request_id_var.set(value)


def get_request_id():
    """获取当前上下文的 request_id，未设置时返回 None。"""
    return _request_id_var.get()


def clear_request_id():
    """清除当前上下文的 request_id。"""
    _request_id_var.set(None)


# LogRecord 的内置属性集合，用于识别用户自定义 extra 字段
_STANDARD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """把日志记录格式化为单行 JSON。"""

    def format(self, record):
        """将 LogRecord 转换为 JSON 字符串。"""
        # 保证 msg 已完成占位符替换
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            message = str(record.msg)

        extra = {}
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            # 保证可序列化，无法序列化时退化为字符串
            try:
                json.dumps(value)
                extra[key] = value
            except (TypeError, ValueError):
                extra[key] = repr(value)

        # 附带异常信息
        if record.exc_info:
            extra["exc_info"] = self.formatException(record.exc_info)

        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": message,
            "request_id": get_request_id(),
            "extra": extra or None,
        }
        # ensure_ascii=False 保留中文，default=str 兜底序列化
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level_name):
    """配置根 logger 使用 JSON 格式的 stdout handler。"""
    if isinstance(level_name, str):
        level = logging.getLevelName(level_name.strip().upper())
        if not isinstance(level, int):
            level = logging.INFO
    else:
        level = logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    # 移除旧的同名 handler，避免重复输出
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(level)
    setattr(handler, _HANDLER_FLAG, True)
    root.addHandler(handler)

    return root


def get_logger(name):
    """获取指定名称的 logger。"""
    return logging.getLogger(name)
