"""feedflow.api —— JSON API 蓝图，挂载于 /api 前缀。"""

from __future__ import annotations

import sqlite3

from flask import Blueprint, current_app, jsonify, request

from . import fetcher, store

bp = Blueprint("api", __name__, url_prefix="/api")


def _db() -> str:
    """从 current_app 配置中取数据库路径。"""
    return current_app.config["FEEDFLOW"]["db_path"]


def _err(msg: str, code: int):
    """统一错误响应体。"""
    return jsonify({"error": msg}), code


def _int_arg(name: str, default=None):
    """解析查询/表单中的整型参数，非法返回 default。"""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _json_body() -> dict:
    """安全获取 JSON 请求体，非法时返回空 dict。"""
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    return {}


# ---------------------------------------------------------------------------
# 分组
# ---------------------------------------------------------------------------

@bp.get("/folders")
def list_folders():
    """列出所有分组，并附带组内源信息。"""
    db = _db()
    folders = store.list_folders(db)
    feeds = store.list_feeds(db, None)
    by_folder: dict = {}
    for f in feeds:
        by_folder.setdefault(f["folder_id"], []).append(f)
    for fo in folders:
        children = by_folder.get(fo["id"], [])
        fo["feeds"] = [
            {
                "id": c["id"],
                "title": c["title"],
                "unread": c.get("unread", 0),
                "enabled": c["enabled"],
                "last_status": c["last_status"],
            }
            for c in children
        ]
    return jsonify(folders)


@bp.post("/folders")
def create_folder():
    """新建分组。"""
    data = _json_body()
    name = (data.get("name") or "").strip()
    if not name:
        return _err("name 必填", 400)
    fid = store.create_folder(_db(), name)
    return jsonify({"id": fid, "name": name}), 201


@bp.put("/folders/<int:folder_id>")
def update_folder(folder_id: int):
    """重命名分组，可选调整 position。"""
    db = _db()
    if store.get_folder(db, folder_id) is None:
        return _err("分组不存在", 404)
    data = _json_body()
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return _err("name 不能为空", 400)
        store.rename_folder(db, folder_id, name)
    if "position" in data:
        try:
            pos = int(data["position"])
        except (TypeError, ValueError):
            return _err("position 非法", 400)
        store.update_folder_position(db, folder_id, pos)
    return jsonify(store.get_folder(db, folder_id))


@bp.delete("/folders/<int:folder_id>")
def delete_folder(folder_id: int):
    """删除分组，组内源 folder_id 置 NULL。"""
    ok = store.delete_folder(_db(), folder_id)
    if not ok:
        return _err("分组不存在", 404)
    return "", 204


# ---------------------------------------------------------------------------
# 文章
# ---------------------------------------------------------------------------

@bp.get("/articles")
def list_articles():
    """按 scope/feed/folder 分页列出文章。"""
    scope = request.args.get("scope") or "unread"
    if scope not in ("unread", "starred", "all"):
        scope = "unread"
    feed_id = _int_arg("feed_id")
    folder_id = _int_arg("folder_id")
    limit = _int_arg("limit", 50)
    offset = _int_arg("offset", 0)
    if limit is None or limit <= 0:
        limit = 50
    limit = min(limit, 200)
    if offset is None or offset < 0:
        offset = 0
    total, articles = store.list_articles(
        _db(),
        scope=scope,
        feed_id=feed_id,
        folder_id=folder_id,
        limit=limit,
        offset=offset,
    )
    return jsonify({"total": total, "articles": articles})


@bp.get("/articles/<int:article_id>")
def get_article(article_id: int):
    """获取单篇文章全字段。"""
    art = store.get_article(_db(), article_id)
    if art is None:
        return _err("文章不存在", 404)
    return jsonify(art)


@bp.post("/articles/<int:article_id>/read")
def set_article_read(article_id: int):
    """设置文章已读/未读。"""
    db = _db()
    if store.get_article(db, article_id) is None:
        return _err("文章不存在", 404)
    data = _json_body()
    if "is_read" not in data:
        return _err("is_read 必填", 400)
    try:
        value = 1 if int(data["is_read"]) else 0
    except (TypeError, ValueError):
        return _err("is_read 非法", 400)
    store.set_read(db, article_id, value)
    return jsonify({"id": article_id, "is_read": value})


@bp.post("/articles/<int:article_id>/star")
def set_article_star(article_id: int):
    """设置文章星标。"""
    db = _db()
    if store.get_article(db, article_id) is None:
        return _err("文章不存在", 404)
    data = _json_body()
    if "is_starred" not in data:
        return _err("is_starred 必填", 400)
    try:
        value = 1 if int(data["is_starred"]) else 0
    except (TypeError, ValueError):
        return _err("is_starred 非法", 400)
    store.set_starred(db, article_id, value)
    return jsonify({"id": article_id, "is_starred": value})


@bp.post("/articles/mark_read")
def mark_all_read():
    """批量标记已读，可按源/分组/范围。"""
    data = _json_body()
    feed_id = data.get("feed_id")
    folder_id = data.get("folder_id")
    scope = data.get("scope") or "unread"
    try:
        feed_id = int(feed_id) if feed_id not in (None, "") else None
    except (TypeError, ValueError):
        return _err("feed_id 非法", 400)
    try:
        folder_id = int(folder_id) if folder_id not in (None, "") else None
    except (TypeError, ValueError):
        return _err("folder_id 非法", 400)
    if scope not in ("unread", "starred", "all"):
        scope = "unread"
    count = store.mark_all_read(_db(), feed_id=feed_id, folder_id=folder_id, scope=scope)
    return jsonify({"updated": count})


# ---------------------------------------------------------------------------
# 源
# ---------------------------------------------------------------------------

@bp.get("/feeds")
def list_feeds():
    """列出全部订阅源（附未读数），供订阅管理页表格使用。"""
    return jsonify(store.list_feeds(_db()))


@bp.post("/feeds")
def create_feed():
    """新建订阅源。"""
    data = _json_body()
    feed_url = (data.get("feed_url") or "").strip()
    if not feed_url:
        return _err("feed_url 必填", 400)
    folder_id = data.get("folder_id")
    try:
        folder_id = int(folder_id) if folder_id not in (None, "") else None
    except (TypeError, ValueError):
        return _err("folder_id 非法", 400)
    interval_min = data.get("interval_min", 0)
    try:
        interval_min = int(interval_min) if interval_min not in (None, "") else 0
    except (TypeError, ValueError):
        return _err("interval_min 非法", 400)
    try:
        fid = store.create_feed(
            _db(), feed_url, folder_id=folder_id, interval_min=interval_min
        )
    except sqlite3.IntegrityError:
        return _err("该订阅源已存在", 409)
    except ValueError as exc:
        return _err(str(exc) or "解析失败", 400)
    return jsonify(store.get_feed(_db(), fid)), 201


@bp.put("/feeds/<int:feed_id>")
def update_feed(feed_id: int):
    """更新源的可编辑字段。"""
    db = _db()
    if store.get_feed(db, feed_id) is None:
        return _err("订阅源不存在", 404)
    data = _json_body()
    allowed = {"title", "folder_id", "interval_min", "enabled", "position"}
    fields: dict = {}
    for key in allowed:
        if key not in data:
            continue
        value = data[key]
        if key in ("folder_id",):
            if value in (None, ""):
                fields[key] = None
            else:
                try:
                    fields[key] = int(value)
                except (TypeError, ValueError):
                    return _err("folder_id 非法", 400)
        elif key in ("interval_min", "enabled", "position"):
            try:
                fields[key] = int(value)
            except (TypeError, ValueError):
                return _err(f"{key} 非法", 400)
        else:
            fields[key] = str(value)
    if fields:
        store.update_feed(db, feed_id, **fields)
    return jsonify(store.get_feed(db, feed_id))


@bp.delete("/feeds/<int:feed_id>")
def delete_feed(feed_id: int):
    """删除源，级联删除其文章。"""
    ok = store.delete_feed(_db(), feed_id)
    if not ok:
        return _err("订阅源不存在", 404)
    return "", 204


@bp.post("/feeds/<int:feed_id>/fetch")
def fetch_feed_now(feed_id: int):
    """立即抓取单个源。"""
    db = _db()
    feed = store.get_feed(db, feed_id)
    if feed is None:
        return _err("订阅源不存在", 404)
    cfg = current_app.config["FEEDFLOW"]
    result = fetcher.fetch_feed(
        db, feed, cfg["user_agent"], extract_timeout=cfg["extract_timeout"]
    )
    return jsonify(result)



# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

@bp.get("/stats")
def get_stats():
    """返回整体统计信息。"""
    return jsonify(store.stats(_db()))
