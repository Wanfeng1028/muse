"""feedflow 应用工厂。

统一契约：
- create_app(cfg=None)：cfg 为空则调用 config.load()。
- 初始化数据库、种子数据、注册蓝图、启动调度器（可用 FEEDFLOW_NO_SCHEDULER=1 关闭）。
"""

from __future__ import annotations

import atexit
import json
import math
import os
import uuid

from flask import Flask, Response, g, jsonify, redirect, request, url_for

from . import auth as _auth
from . import config as _config
from . import db as _db
from . import scheduler as _scheduler
from . import seed as _seed
from .logging import clear_request_id, get_logger, set_request_id, setup_logging

_logger = get_logger("feedflow.metrics")


def create_app(cfg=None) -> Flask:
    """创建 Flask 应用实例。"""
    if cfg is None:
        cfg = _config.load()

    # 配置校验：fail fast，避免带着非法配置继续初始化
    _config.validate(cfg)

    # 初始化日志系统（使用配置中的日志级别）
    setup_logging(cfg["log_level"])

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    db_path = cfg["db_path"]

    # 初始化数据库（建表、FTS、trigger、索引）
    _db.init_db(db_path)

    # 种子数据：仅在 feeds 表为空时插入示例源
    _seed.ensure_seed(db_path)

    # 将配置挂到 app.config，供蓝图内通过 current_app 读取
    app.config["FEEDFLOW"] = cfg

    if cfg.get("secret_key"):
        app.secret_key = cfg["secret_key"]

    # 登录失败锁定器（内存计数，每应用实例独立；测试用 create_app 各自独立不串计数）。
    from .login_lockout import LoginLockout

    app.extensions["FEEDFLOW_LOGIN_LOCKOUT"] = LoginLockout(
        max_attempts=int(cfg.get("auth_max_attempts", 5)),
        window_seconds=int(cfg.get("auth_window_seconds", 900)),
        lock_seconds=int(cfg.get("auth_lock_seconds", 900)),
    )

    # HTTP 层 IP 限流器（内存令牌桶），create_app 内只创建一次，闭包引用。
    from .ratelimit import RateLimiter

    _limiter = RateLimiter(
        rate_per_sec=float(cfg["rate_limit_rps"]),
        burst=int(cfg["rate_limit_burst"]),
    )

    # 注册蓝图（延迟导入避免循环依赖）
    from .api import bp as api_bp
    from .fever import fever_bp
    from .web import bp as web_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(fever_bp)
    from .auth import auth_bp

    app.register_blueprint(auth_bp)

    @app.before_request
    def _bind_request_id() -> None:
        """为每个请求生成或复用 request_id，并写入日志上下文。"""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        set_request_id(request_id)
        g.request_id = request_id

    @app.before_request
    def _check_auth_gate():
        """密码门：未开启直接放行；放行 /healthz、/metrics、/login、/logout、/static/*、/fever/*；其余未登录时 /api/* 回 401 JSON，其他页重定向到登录页。"""
        cfg = app.config["FEEDFLOW"]
        if not _auth.is_auth_enabled(cfg):
            return None
        if request.path in ("/healthz", "/metrics", "/login", "/logout"):
            return None
        if request.path.startswith(("/static/", "/fever/")):
            return None
        if _auth.is_logged_in():
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "需要登录"}), 401
        return redirect(url_for("auth.login", next=request.path))

    @app.before_request
    def _check_rate_limit():
        """HTTP 层 IP 限流：命中拒绝时短路返回 429。"""
        cfg = app.config["FEEDFLOW"]
        if not cfg.get("rate_limit_enabled"):
            return None

        # 免限流路径：精确匹配，避免前缀匹配误伤。
        if request.path in ("/healthz", "/metrics"):
            return None

        key = request.remote_addr or "unknown"
        ok, retry_after = _limiter.allow(key)
        if ok:
            return None

        try:
            from . import metrics as _metrics

            _metrics.inc_rate_limited()
        except Exception as exc:  # noqa: BLE001  # 埋点不许影响限流主流程，故意宽捕获
            _logger.warning("限流埋点失败", extra={"error": str(exc)[:200]})

        return Response(
            json.dumps({"error": "请求过于频繁，请稍后再试"}, ensure_ascii=False),
            status=429,
            mimetype="application/json",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )

    @app.after_request
    def _write_back_request_id(response):
        """将 request_id 写回响应头，并清理日志上下文。"""
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        try:
            from . import metrics as _metrics

            _metrics.inc_http_request(
                request.method,
                getattr(request.url_rule, "rule", None) or "unknown",
                str(response.status_code),
            )
        except Exception as exc:  # noqa: BLE001  # 指标埋点不许影响请求主流程，故意宽捕获
            _logger.warning("指标埋点失败", extra={"error": str(exc)[:200]})
        clear_request_id()
        return response

    @app.teardown_request
    def _clear_request_id_on_teardown(exc) -> None:
        """请求结束兜底清理，防止上下文泄漏到下一个请求。"""
        clear_request_id()

    # 启动后台调度器（测试时可用 FEEDFLOW_NO_SCHEDULER=1 关闭）
    if os.environ.get("FEEDFLOW_NO_SCHEDULER") != "1":
        _scheduler.start_scheduler(app)

        def _shutdown() -> None:
            _scheduler.shutdown_scheduler()

        atexit.register(_shutdown)

    return app
