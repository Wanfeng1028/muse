"""Web 蓝图：服务端渲染页面 + OPML 导入导出。"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from . import opml, store

bp = Blueprint("web", __name__)


def _cfg() -> dict:
    """从应用配置里取出 feedflow 配置字典。"""
    return current_app.config["FEEDFLOW"]


@bp.get("/")
def index():
    """阅读器主页：服务端渲染分组/源树，文章列表由前端 JS 调 API 加载。"""
    db_path = _cfg()["db_path"]
    folders = store.list_folders(db_path)
    # 每个分组附带其下的源，供左侧树展示
    for folder in folders:
        folder["feeds"] = store.list_feeds(db_path, folder_id=folder["id"])
    # 未分组（folder_id 为 NULL）的源单独展示
    ungrouped = store.list_feeds(db_path, folder_id=None)
    ungrouped = [f for f in ungrouped if f.get("folder_id") is None]
    stats = store.stats(db_path)
    return render_template(
        "reader.html",
        folders=folders,
        ungrouped=ungrouped,
        stats=stats,
    )


@bp.get("/feeds")
def feeds_page():
    """订阅管理页：新建表单 + 源表格 + 分组管理。"""
    db_path = _cfg()["db_path"]
    feeds = store.list_feeds(db_path)
    folders = store.list_folders(db_path)
    return render_template("feeds.html", feeds=feeds, folders=folders)


@bp.get("/stats")
def stats_page():
    """统计页。"""
    db_path = _cfg()["db_path"]
    return render_template("stats.html", stats=store.stats(db_path))


@bp.get("/opml")
def opml_page():
    """OPML 导入导出页。"""
    imported = request.args.get("imported")
    skipped = request.args.get("skipped")
    result = None
    if imported is not None or skipped is not None:
        result = {
            "imported": int(imported or 0),
            "skipped": int(skipped or 0),
        }
    return render_template("opml.html", result=result)


@bp.get("/opml/export")
def opml_export():
    """导出 OPML 文件下载。"""
    db_path = _cfg()["db_path"]
    xml_text = opml.export_opml(db_path)
    return Response(
        xml_text,
        mimetype="text/xml",
        headers={"Content-Disposition": "attachment; filename=feedflow.opml"},
    )


@bp.post("/opml/import")
def opml_import():
    """接收上传的 OPML 文件并导入。"""
    db_path = _cfg()["db_path"]
    file = request.files.get("file")
    if file is None:
        return redirect(url_for("web.opml_page", imported=0, skipped=0))
    try:
        xml_text = file.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001  # 解码失败则按空处理，故意宽捕获
        xml_text = ""
    result = opml.import_opml(db_path, xml_text)
    return redirect(
        url_for(
            "web.opml_page",
            imported=result.get("imported", 0),
            skipped=result.get("skipped", 0),
        )
    )


@bp.get("/search")
def search_page():
    """搜索结果页。"""
    db_path = _cfg()["db_path"]
    q = request.args.get("q", "")
    articles = store.search_articles(db_path, q) if q.strip() else []
    return render_template("search.html", q=q, articles=articles)


@bp.get("/healthz")
def healthz():
    """健康检查：返回服务、数据库与调度器状态。"""
    db_path = _cfg()["db_path"]

    # 数据库探活：执行 SELECT 1
    db_status = "ok"
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception:  # noqa: BLE001  # 探活失败视为 degraded，故意宽捕获
        db_status = "error"

    # 调度器状态：从 feedflow.scheduler._scheduler 判断
    scheduler_status = "disabled"
    try:
        from . import scheduler as _scheduler

        sched = getattr(_scheduler, "_scheduler", None)
        if sched is not None and getattr(sched, "running", False):
            scheduler_status = "running"
    except Exception:  # noqa: BLE001  # 导入或属性异常时保持 disabled
        scheduler_status = "disabled"

    status = "ok" if db_status == "ok" else "degraded"

    payload = {
        "status": status,
        "version": "0.2.0",
        "db": db_status,
        "scheduler": scheduler_status,
        "now": datetime.now(UTC).isoformat(),
    }
    return Response(
        __import__("json").dumps(payload, ensure_ascii=False),
        mimetype="application/json",
    )
