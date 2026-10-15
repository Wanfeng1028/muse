"""feedflow 应用工厂。

统一契约：
- create_app(cfg=None)：cfg 为空则调用 config.load()。
- 初始化数据库、种子数据、注册蓝图、启动调度器（可用 FEEDFLOW_NO_SCHEDULER=1 关闭）。
"""

from __future__ import annotations

import atexit
import os
import uuid

from flask import Flask, g, request

from . import config as _config
from . import db as _db
from . import scheduler as _scheduler
from . import seed as _seed
from .logging import clear_request_id, set_request_id, setup_logging


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

    # 注册蓝图（延迟导入避免循环依赖）
    from .api import bp as api_bp
    from .fever import fever_bp
    from .web import bp as web_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(fever_bp)

    @app.before_request
    def _bind_request_id() -> None:
        """为每个请求生成或复用 request_id，并写入日志上下文。"""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        set_request_id(request_id)
        g.request_id = request_id

    @app.after_request
    def _write_back_request_id(response):
        """将 request_id 写回响应头，并清理日志上下文。"""
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
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
