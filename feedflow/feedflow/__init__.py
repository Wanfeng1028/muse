"""feedflow 应用工厂。

统一契约：
- create_app(cfg=None)：cfg 为空则调用 config.load()。
- 初始化数据库、种子数据、注册蓝图、启动调度器（可用 FEEDFLOW_NO_SCHEDULER=1 关闭）。
"""
from __future__ import annotations

import atexit

from flask import Flask

from . import config as _config
from . import db as _db
from . import scheduler as _scheduler
from . import seed as _seed


def create_app(cfg=None) -> Flask:
    """创建 Flask 应用实例。"""
    if cfg is None:
        cfg = _config.load()

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
    from .web import bp as web_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    # 启动后台调度器（测试时可用 FEEDFLOW_NO_SCHEDULER=1 关闭）
    import os

    if os.environ.get("FEEDFLOW_NO_SCHEDULER") != "1":
        _scheduler.start_scheduler(app)

        def _shutdown() -> None:
            _scheduler.shutdown_scheduler()

        atexit.register(_shutdown)

    return app
