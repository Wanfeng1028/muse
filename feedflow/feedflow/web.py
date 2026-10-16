"""Web 蓝图：服务端渲染页面 + OPML 导入导出。

v1.2：新增摘要（digest）与兴趣设置页面。
"""
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

from . import opml, ranking, store

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


@bp.get("/metrics")
def metrics():
    """Prometheus 指标。"""
    from . import metrics as metrics_mod

    db_path = _cfg()["db_path"]
    text = metrics_mod.render(db_path)
    return Response(text, mimetype="text/plain; version=0.0.4")


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


@bp.get("/digest")
def digest_page():
    """摘要页：按兴趣权重取 N 篇未读文章。"""
    db_path = _cfg()["db_path"]
    n = ranking.get_digest_n(db_path, default=int(_cfg().get("digest_n") or 20))
    if n <= 0:
        n = 20
    items = ranking.get_digest(db_path, n)
    return render_template(
        "digest.html",
        items=items,
        n=n,
        today=datetime.now(UTC).date().isoformat(),
    )


@bp.get("/settings/interests")
def interests_page():
    """兴趣设置页：关键词、源权重、摘要篇数。"""
    db_path = _cfg()["db_path"]
    keywords = ranking.get_keywords(db_path)
    feed_weights = ranking.get_feed_weights(db_path)
    digest_n = ranking.get_digest_n(db_path, default=int(_cfg().get("digest_n") or 20))
    saved = request.args.get("saved")
    err = request.args.get("err")
    return render_template(
        "interests.html",
        keywords=keywords,
        feed_weights=feed_weights,
        digest_n=digest_n,
        saved=saved,
        err=err,
    )


@bp.post("/settings/interests/keywords")
def interests_add_keyword():
    """新增兴趣关键词。"""
    db_path = _cfg()["db_path"]
    kw = (request.form.get("keyword") or "").strip()
    if not kw:
        return redirect(url_for("web.interests_page", err="empty"))
    try:
        ranking.add_keyword(db_path, kw)
    except ValueError:
        return redirect(url_for("web.interests_page", err="empty"))
    return redirect(url_for("web.interests_page", saved="1"))


@bp.post("/settings/interests/keywords/<int:kid>/delete")
def interests_delete_keyword(kid: int):
    """删除兴趣关键词。"""
    db_path = _cfg()["db_path"]
    ranking.delete_keyword(db_path, kid)
    return redirect(url_for("web.interests_page", saved="1"))


@bp.post("/settings/interests/feeds/<int:fid>/weight")
def interests_set_weight(fid: int):
    """设置某个源的兴趣权重。"""
    db_path = _cfg()["db_path"]
    raw = (request.form.get("weight") or "").strip()
    try:
        w = float(raw)
        ranking.set_feed_weight(db_path, fid, w)
    except (ValueError, TypeError):
        return redirect(url_for("web.interests_page", err="weight"))
    return redirect(url_for("web.interests_page", saved="1"))


@bp.post("/settings/interests/digest_n")
def interests_set_digest_n():
    """设置摘要页文章数量。"""
    db_path = _cfg()["db_path"]
    raw = (request.form.get("n") or "").strip()
    try:
        n = int(raw)
        assert n >= 1
        ranking.set_setting(db_path, "digest_n", n)
    except (ValueError, TypeError, AssertionError):
        return redirect(url_for("web.interests_page", err="n"))
    return redirect(url_for("web.interests_page", saved="1"))
