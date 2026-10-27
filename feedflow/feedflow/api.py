"""feedflow.api —— JSON API 蓝图，挂载于 /api 前缀。"""

from __future__ import annotations

import sqlite3
from datetime import UTC

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


@bp.post("/folders/<int:folder_id>/move")
def move_folder(folder_id: int):
    """上/下移动分组。"""
    db = _db()
    folder = store.get_folder(db, folder_id)
    if folder is None:
        return _err("分组不存在", 404)
    data = _json_body()
    direction = data.get("direction")
    if direction not in ("up", "down"):
        return _err("direction 非法", 400)
    moved = store.move_folder(db, folder_id, direction)
    return jsonify({"moved": bool(moved), "folder": store.get_folder(db, folder_id)})


# ---------------------------------------------------------------------------
# 文章
# ---------------------------------------------------------------------------

@bp.get("/articles")
def list_articles():
    """按 scope/feed/folder 分页列出文章。"""
    scope = request.args.get("scope") or "unread"
    if scope not in ("unread", "starred", "all"):
        return _err("scope 非法", 400)
    raw_feed_id = request.args.get("feed_id")
    if raw_feed_id is None or raw_feed_id == "":
        feed_id = None
    else:
        try:
            feed_id = int(raw_feed_id)
        except (TypeError, ValueError):
            return _err("feed_id 参数非法", 400)
    raw_folder_id = request.args.get("folder_id")
    if raw_folder_id is None or raw_folder_id == "":
        folder_id = None
    else:
        try:
            folder_id = int(raw_folder_id)
        except (TypeError, ValueError):
            return _err("folder_id 参数非法", 400)
    raw_tag_id = request.args.get("tag_id")
    if raw_tag_id is None or raw_tag_id == "":
        tag_id = None
    else:
        try:
            tag_id = int(raw_tag_id)
        except (TypeError, ValueError):
            return _err("tag_id 参数非法", 400)
    raw_limit = request.args.get("limit")
    if raw_limit is None or raw_limit == "":
        limit = 50
    else:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return _err("limit 参数非法", 400)
        if limit < 1:
            return _err("limit 参数非法", 400)
    limit = min(limit, 200)
    raw_offset = request.args.get("offset")
    if raw_offset is None or raw_offset == "":
        offset = 0
    else:
        try:
            offset = int(raw_offset)
        except (TypeError, ValueError):
            return _err("offset 参数非法", 400)
        if offset < 0:
            return _err("offset 参数非法", 400)
    total, articles = store.list_articles(
        _db(),
        scope=scope,
        feed_id=feed_id,
        folder_id=folder_id,
        tag_id=tag_id,
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


@bp.get("/articles/<int:article_id>/score")
def get_article_score(article_id: int):
    """排序可解释性：返回该篇文章的重要性评分与五个因子的得分明细。"""
    from datetime import datetime

    from . import db, ranking
    art = store.get_article(_db(), article_id)
    if art is None:
        return _err("文章不存在", 404)
    db_path = _db()
    feed_id = art.get("feed_id")
    fw = next((w for w in ranking.get_feed_weights(db_path) if w["feed_id"] == feed_id), None)
    feed_weight = fw["weight"] if fw else 1.0
    learned = fw["learned"] if fw else 1.0
    cluster_id = art.get("cluster_id")
    if cluster_id:
        members = db.query_all(db_path, "SELECT id FROM articles WHERE cluster_id = ?", (cluster_id,))
        cluster_size = len(members)
    else:
        cluster_size = 1
    info = ranking.score_article(
        art,
        now=datetime.now(UTC),
        cluster_size=cluster_size,
        feed_weight=feed_weight,
        learned=learned,
        keywords=ranking.get_keywords(db_path),
    )
    return jsonify({"article_id": article_id, "title": art.get("title"), **info})


@bp.get("/clusters")
def list_clusters():
    """聚类浏览：同事件多源报道折叠视图（SimHash+Jaccard 两阶段聚类，非 LLM）。"""
    from . import ranking
    n = _int_arg("n", 10)
    clusters = ranking.get_digest_clusters(_db(), n)
    return jsonify({"clusters": clusters, "total": len(clusters)})


@bp.post("/clusters/<int:cluster_id>/read")
def mark_cluster_read(cluster_id: int):
    """按簇标记已读；solo 单篇按自身 id 命中；已全部已读时 updated 为 0 且仍返回 200（幂等）。"""
    body = _json_body()
    scope = body.get("scope", "unread")
    if scope not in ("unread", "starred", "all"):
        return _err("scope 非法", 400)
    if not store.cluster_exists(_db(), cluster_id):
        return _err("聚类不存在", 404)
    count = store.mark_cluster_read(_db(), cluster_id, scope=scope)
    return jsonify({"cluster_id": cluster_id, "updated": count})


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
    article = store.get_article(db, article_id)
    return jsonify({
        "id": article_id,
        "is_starred": value,
        "starred_at": article["starred_at"] if article is not None else None,
    })



@bp.post("/articles/<int:article_id>/archive")
def set_article_archive(article_id: int):
    """设置文章归档。"""
    db = _db()
    if store.get_article(db, article_id) is None:
        return _err("文章不存在", 404)
    data = _json_body()
    if "is_archived" not in data:
        return _err("is_archived 必填", 400)
    try:
        value = 1 if int(data["is_archived"]) else 0
    except (TypeError, ValueError):
        return _err("is_archived 非法", 400)
    store.set_archived(db, article_id, value)
    article = store.get_article(db, article_id)
    return jsonify({
        "id": article_id,
        "is_archived": value,
        "archived_at": article["archived_at"] if article is not None else None,
    })


@bp.post("/articles/<int:article_id>/progress")
def set_article_progress(article_id: int):
    """记录阅读进度。body: {"scroll_pos": 数字}。"""
    db = _db()
    if store.get_article(db, article_id) is None:
        return _err("文章不存在", 404)
    data = _json_body()
    if "scroll_pos" not in data:
        return _err("scroll_pos 必填", 400)
    try:
        value = float(data["scroll_pos"])
    except (TypeError, ValueError):
        return _err("scroll_pos 非法", 400)
    if value < 0:
        return _err("scroll_pos 非法", 400)
    if value > 100000:
        value = 100000.0
    store.set_scroll_pos(db, article_id, value)
    return jsonify({"id": article_id, "scroll_pos": value})


@bp.post("/articles/mark_read")
def mark_all_read():
    """批量标记已读，可按源/分组/范围。"""
    data = _json_body()
    feed_id = data.get("feed_id")
    folder_id = data.get("folder_id")
    tag_id = data.get("tag_id")
    scope = data.get("scope") or "unread"
    try:
        feed_id = int(feed_id) if feed_id not in (None, "") else None
    except (TypeError, ValueError):
        return _err("feed_id 非法", 400)
    try:
        folder_id = int(folder_id) if folder_id not in (None, "") else None
    except (TypeError, ValueError):
        return _err("folder_id 非法", 400)
    try:
        tag_id = int(tag_id) if tag_id not in (None, "") else None
    except (TypeError, ValueError):
        return _err("tag_id 非法", 400)
    if scope not in ("unread", "starred", "all"):
        scope = "unread"
    count = store.mark_all_read(_db(), feed_id=feed_id, folder_id=folder_id, tag_id=tag_id, scope=scope)
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


@bp.post("/feeds/<int:feed_id>/reactivate")
def reactivate_feed(feed_id: int):
    """手动复活死源。"""
    db = _db()
    if not store.reactivate_feed(db, feed_id):
        return _err("订阅源不存在", 404)
    return jsonify(store.get_feed(db, feed_id))



# ---------------------------------------------------------------------------
# 标签
# ---------------------------------------------------------------------------

@bp.get("/tags")
def list_tags():
    return jsonify({"tags": store.list_tags(_db())})


@bp.post("/tags")
def create_tag():
    body = _json_body()
    name = str(body.get("name") or "").strip()
    if not name: return _err("标签名为空", 400)
    try: tag = store.create_tag(_db(), name)
    except ValueError: return _err("标签名为空", 400)
    return jsonify(tag), 201


@bp.get("/articles/<int:article_id>/tags")
def list_article_tags(article_id):
    if not store.get_article(_db(), article_id): return _err("文章不存在", 404)
    return jsonify({"article_id": article_id, "tags": store.list_article_tags(_db(), article_id)})


@bp.post("/articles/<int:article_id>/tags")
def add_article_tag(article_id):
    if not store.get_article(_db(), article_id): return _err("文章不存在", 404)
    body = _json_body()
    tag_id = body.get("tag_id")
    if tag_id is None:
        name = str(body.get("name") or "").strip()
        if not name: return _err("标签名为空", 400)
        try: tag_id = store.create_tag(_db(), name)["id"]
        except ValueError: return _err("标签名为空", 400)
    elif not any(t.get("id") == tag_id for t in store.list_tags(_db())):
        return _err("标签不存在", 404)
    return jsonify({"article_id": article_id, "tag_id": tag_id, "added": store.add_article_tag(_db(), article_id, tag_id)})


@bp.delete("/articles/<int:article_id>/tags/<int:tag_id>")
def remove_article_tag(article_id, tag_id):
    if not store.get_article(_db(), article_id): return _err("文章不存在", 404)
    return jsonify({"article_id": article_id, "tag_id": tag_id, "removed": store.remove_article_tag(_db(), article_id, tag_id)})

# ---------------------------------------------------------------------------
# 阅读笔记
# ---------------------------------------------------------------------------

@bp.route("/notes", methods=["GET"])
def list_notes():
    return jsonify({"notes": store.list_notes(_db())})


@bp.route("/articles/<int:article_id>/note", methods=["GET"])
def get_article_note(article_id):
    if store.get_article(_db(), article_id) is None:
        return _err("文章不存在", 404)
    return jsonify(store.get_note(_db(), article_id))


@bp.route("/articles/<int:article_id>/note", methods=["PUT"])
def save_article_note(article_id):
    if store.get_article(_db(), article_id) is None:
        return _err("文章不存在", 404)
    body = str(_json_body().get("body") or "")
    if not body.strip():
        return _err("笔记内容为空", 400)
    try:
        return jsonify(store.save_note(_db(), article_id, body))
    except ValueError:
        return _err("笔记内容为空", 400)


@bp.route("/articles/<int:article_id>/note", methods=["DELETE"])
def delete_article_note(article_id):
    if store.get_article(_db(), article_id) is None:
        return _err("文章不存在", 404)
    return jsonify({"article_id": article_id, "removed": store.delete_note(_db(), article_id)})

# ---------------------------------------------------------------------------
# 稍后读队列
# ---------------------------------------------------------------------------

# ---- 稍后读队列 ----


@bp.get("/later")
def list_later():
    """获取稍后读队列中的全部文章。"""
    return jsonify({"later": store.list_later(_db())})


@bp.route("/articles/<int:article_id>/later", methods=["GET"])
def get_article_later(article_id):
    """查询文章是否在稍后读队列中。

    文章不存在时返回 404 错误；否则返回该文章的排队状态。
    """
    if store.get_article(_db(), article_id) is None:
        return _err("文章不存在", 404)
    return jsonify({"article_id": article_id, "queued": store.is_queued(_db(), article_id)})


@bp.post("/articles/<int:article_id>/later")
def queue_later(article_id):
    """将文章加入稍后读队列；已在队列中时 queued 为 False，仍返回 200。"""
    if store.get_article(_db(), article_id) is None:
        return _err("文章不存在", 404)
    return jsonify({"article_id": article_id, "queued": store.queue_article(_db(), article_id)})


@bp.delete("/articles/<int:article_id>/later")
def remove_later(article_id):
    """将文章移出稍后读队列。"""
    if store.get_article(_db(), article_id) is None:
        return _err("文章不存在", 404)
    return jsonify({"article_id": article_id, "removed": store.dequeue_article(_db(), article_id)})


@bp.post("/articles/<int:article_id>/later/move")
def move_later(article_id):
    """在稍后读队列中上移或下移指定文章，direction 取值限 up/down。"""
    if store.get_article(_db(), article_id) is None:
        return _err("文章不存在", 404)
    direction = _json_body().get("direction")
    if direction not in ("up", "down"):
        return _err("direction 非法", 400)
    return jsonify({"article_id": article_id, "moved": store.move_later(_db(), article_id, direction)})


# ---------------- 阅读历史 ----------------

@bp.get("/history")
def list_history():
    return jsonify({"history": store.list_history(_db())})


@bp.post("/articles/<int:article_id>/history")
def record_article_history(article_id):
    if store.get_article(_db(), article_id) is None:
        return _err("文章不存在", 404)
    entry = store.record_history(_db(), article_id)
    return jsonify({"article_id": article_id, "recorded": True, "read_count": entry["read_count"], "last_read_at": entry["last_read_at"]})


@bp.delete("/history")
def clear_history_api():
    return jsonify({"cleared": store.clear_history(_db())})


# ---------------- 星标收藏 ----------------

@bp.get("/starred")
def list_starred_api():
    """列出星标文章。"""
    return jsonify({"starred": store.list_starred(_db())})




# ---------------- 文章归档 ----------------

@bp.get("/archived")
def list_archived_api():
    """列出归档文章。"""
    return jsonify({"archived": store.list_archived(_db())})


# ---------------------------------------------------------------------------
# 保存的搜索
# ---------------------------------------------------------------------------


@bp.get("/saved-searches")
def list_saved_searches():
    return jsonify({"saved_searches": store.list_saved_searches(_db())})


@bp.post("/saved-searches")
def add_saved_search():
    body = _json_body()
    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        return _err("搜索词为空", 400)
    try:
        row = store.save_search(_db(), query)
    except ValueError:
        return _err("搜索词为空", 400)
    return jsonify(row)


@bp.delete("/saved-searches/<int:search_id>")
def remove_saved_search(search_id):
    if not store.delete_saved_search(_db(), search_id):
        return _err("保存的搜索不存在", 404)
    return jsonify({"id": search_id, "removed": True})

# ---------------------------------------------------------------------------
# 阅读清单
# ---------------------------------------------------------------------------


@bp.get("/reading-lists")
def get_reading_lists():
    return jsonify({"reading_lists": store.list_reading_lists(_db())})


@bp.post("/reading-lists")
def add_reading_list():
    body = _json_body()
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return _err("清单名为空", 400)
    try:
        row = store.create_reading_list(_db(), name.strip())
    except ValueError:
        return _err("清单名为空", 400)
    return jsonify(row)


@bp.delete("/reading-lists/<int:list_id>")
def remove_reading_list(list_id):
    if not store.delete_reading_list(_db(), list_id):
        return _err("阅读清单不存在", 404)
    return jsonify({"id": list_id, "removed": True})


@bp.get("/reading-lists/<int:list_id>/articles")
def get_reading_list_articles(list_id):
    articles = store.list_reading_list_articles(_db(), list_id)
    if articles is None:
        return _err("阅读清单不存在", 404)
    return jsonify({"list_id": list_id, "articles": articles})


@bp.post("/reading-lists/<int:list_id>/articles")
def add_article_to_reading_list(list_id):
    body = _json_body()
    article_id = body.get("article_id")
    if not isinstance(article_id, int) or isinstance(article_id, bool):
        return _err("article_id 非法", 400)
    if store.get_reading_list(_db(), list_id) is None:
        return _err("阅读清单不存在", 404)
    row = store.add_article_to_list(_db(), list_id, article_id)
    if row is None:
        return _err("文章不存在", 404)
    return jsonify(row)


@bp.delete("/reading-lists/<int:list_id>/articles/<int:article_id>")
def remove_article_from_reading_list(list_id, article_id):
    if store.get_reading_list(_db(), list_id) is None:
        return _err("阅读清单不存在", 404)
    if not store.remove_article_from_list(_db(), list_id, article_id):
        return _err("文章不在清单中", 404)
    return jsonify({"list_id": list_id, "article_id": article_id, "removed": True})


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

@bp.get("/stats")
def get_stats():
    """返回整体统计信息。"""
    return jsonify(store.stats(_db()))
