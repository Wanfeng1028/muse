
"""Fever API 兼容层。

这个模块让第三方 RSS 阅读器（Reeder、Unread 等仍支持 Fever 协议的客户端）
能连上 FeedFlow 同步订阅、未读和星标状态。

Fever 协议要点（照官方文档实现）：
- 鉴权用 POST 提交 api_key，值是 md5(email:password) 的十六进制。
  认证成功响应里必须带 "api_version": 3 和 "auth": 1，失败带 "auth": 0。
- 读参数放 URL query string，比如 POST /fever/?api&groups，注意 ?api 没有值。
  写参数放 POST form 里。多个读参数可以组合，要分别处理再合并进同一个响应。

本实现的几处如实说明（不是偷懒，是能力边界）：
- group 0 代表"未分组"的源，mark=group&id=0 视为标记全部源。
- feeds 里的 is_spark 恒为 0，本实现没有 spark 这个概念。
- favicons 没做真正的抓取，固定返回一个 1x1 透明 GIF 占位。
"""

import hmac
from datetime import UTC, datetime, timedelta

from flask import Blueprint, current_app, jsonify, request

from . import db as db_module
from . import store

fever_bp = Blueprint("fever", __name__)

# 1x1 透明 GIF 的 data URI，给 favicon 占位用。
_PLACEHOLDER_FAVICON = (
    "data:image/gif;base64,"
    "R0lGODlhAQABAIAAAP///////yH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
)


def _cfg():
    """取 FeedFlow 的配置字典，拿不到就给个空字典兜底。"""
    return current_app.config.get("FEEDFLOW", {})


def _db_path():
    """当前应用的数据库路径。"""
    return _cfg().get("db_path")


def _api_key_ok():
    """校验请求里的 api_key。

    配置里没设 fever_api_key 就直接认证失败（等于功能没开）。
    否则比较配置值和请求里的 api_key，用 hmac.compare_digest 防时序攻击。
    """
    expected = _cfg().get("fever_api_key") or ""
    if not expected:
        return False
    supplied = request.form.get("api_key") or request.args.get("api_key") or ""
    return hmac.compare_digest(str(expected), str(supplied))


def _to_unix(iso):
    """把 ISO 时间字符串转成 Unix 时间戳整数。

    空值或解析失败都返回 0。datetime.fromisoformat 能处理带 +00:00 后缀的。
    """
    if not iso:
        return 0
    try:
        dt = datetime.fromisoformat(str(iso))
    except (ValueError, TypeError):
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())


def _now_iso():
    """当前 UTC 时间的 ISO 字符串。"""
    return datetime.now(UTC).isoformat()


def _article_to_item(row):
    """把 articles 表的一行 dict 转成 Fever 的 item 结构。"""
    html = row.get("content_html") or row.get("summary") or ""
    created = _to_unix(row.get("published_at") or row.get("fetched_at"))
    return {
        "id": row.get("id"),
        "feed_id": row.get("feed_id"),
        "title": row.get("title") or "",
        "author": row.get("author") or "",
        "html": html,
        "url": row.get("link") or "",
        "is_saved": 1 if row.get("is_starred") else 0,
        "is_read": 1 if row.get("is_read") else 0,
        "created_on_time": created,
    }


def _parse_int(value):
    """把字符串转 int，转不了返回 None。"""
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _build_feeds_groups(db_path, feeds):
    """根据 feeds 列表组装 feeds_groups。

    每个 folder 一条记录，feed_ids 是该组内 feed id 升序的逗号串。
    folder_id 为 NULL 的源归入 group 0（未分组）。
    """
    by_folder = {}
    ungrouped = []
    for f in feeds:
        fid = f.get("folder_id")
        if fid is None:
            ungrouped.append(f["id"])
        else:
            by_folder.setdefault(fid, []).append(f["id"])

    result = []
    for folder_id in sorted(by_folder.keys()):
        ids = sorted(by_folder[folder_id])
        result.append(
            {"group_id": folder_id, "feed_ids": ",".join(str(i) for i in ids)}
        )

    if ungrouped:
        ids = sorted(ungrouped)
        result.append({"group_id": 0, "feed_ids": ",".join(str(i) for i in ids)})

    return result


def _read_groups(db_path, resp):
    """处理 groups 读参数：groups 和 feeds_groups。"""
    folders = store.list_folders(db_path)
    feeds = store.list_feeds(db_path)

    resp["groups"] = [{"id": f["id"], "title": f["name"]} for f in folders]
    resp["feeds_groups"] = _build_feeds_groups(db_path, feeds)
    return resp


def _read_feeds(db_path, resp):
    """处理 feeds 读参数：feeds 和 feeds_groups。"""
    feeds = store.list_feeds(db_path)

    items = []
    for f in feeds:
        last_updated = _to_unix(f.get("last_fetched_at") or f.get("created_at"))
        items.append(
            {
                "id": f["id"],
                "favicon_id": 1,
                "title": f.get("title") or "",
                "url": f.get("feed_url") or "",
                "site_url": f.get("site_url") or "",
                "is_spark": 0,
                "last_updated_on_time": last_updated,
            }
        )
    resp["feeds"] = items
    resp["feeds_groups"] = _build_feeds_groups(db_path, feeds)
    return resp


def _read_favicons(resp):
    """处理 favicons 读参数，固定返回占位图。"""
    resp["favicons"] = [{"id": 1, "data": _PLACEHOLDER_FAVICON}]
    return resp


def _read_items(db_path, resp):
    """处理 items 读参数，支持 since_id / max_id / with_ids 分页。

    非法参数返回 (resp, 400)，正常返回 (resp, None)。
    """
    since_id = request.args.get("since_id")
    max_id = request.args.get("max_id")
    with_ids = request.args.get("with_ids")

    params = []
    where = ""
    order = "id DESC"

    if with_ids is not None:
        id_strs = [s.strip() for s in str(with_ids).split(",") if s.strip()]
        if not id_strs:
            return resp, 400
        id_vals = []
        for s in id_strs:
            v = _parse_int(s)
            if v is None:
                return resp, 400
            id_vals.append(v)
        id_vals = id_vals[:50]
        placeholders = ",".join("?" for _ in id_vals)
        where = f"WHERE id IN ({placeholders})"
        params = id_vals
        order = "id DESC"
    elif since_id is not None:
        v = _parse_int(since_id)
        if v is None:
            return resp, 400
        where = "WHERE id > ?"
        params = [v]
        order = "id ASC"
    elif max_id is not None:
        v = _parse_int(max_id)
        if v is None:
            return resp, 400
        where = "WHERE id < ?"
        params = [v]
        order = "id DESC"
    else:
        order = "id DESC"

    sql = (
        "SELECT id, feed_id, title, author, link, summary, content_html, "
        "published_at, fetched_at, is_read, is_starred "
        f"FROM articles {where} ORDER BY {order} LIMIT 50"
    )
    rows = db_module.query_all(db_path, sql, params)
    resp["items"] = [_article_to_item(r) for r in rows]

    total_row = db_module.query_one(db_path, "SELECT COUNT(*) AS c FROM articles", [])
    resp["total_items"] = total_row["c"] if total_row else 0
    return resp, None


def _read_unread_item_ids(db_path, resp):
    """处理 unread_item_ids 读参数，返回逗号分隔的 id 串。"""
    rows = db_module.query_all(
        db_path, "SELECT id FROM articles WHERE is_read = 0 ORDER BY id", []
    )
    resp["unread_item_ids"] = ",".join(str(r["id"]) for r in rows)
    return resp


def _read_saved_item_ids(db_path, resp):
    """处理 saved_item_ids 读参数，返回逗号分隔的 id 串。"""
    rows = db_module.query_all(
        db_path, "SELECT id FROM articles WHERE is_starred = 1 ORDER BY id", []
    )
    resp["saved_item_ids"] = ",".join(str(r["id"]) for r in rows)
    return resp


def _handle_read_params(db_path, resp):
    """按 query string 里的读参数逐个处理，合并进同一个响应。

    返回 (resp, status)。status 为 None 表示正常。
    """
    if "groups" in request.args:
        _read_groups(db_path, resp)
    if "feeds" in request.args:
        _read_feeds(db_path, resp)
    if "favicons" in request.args:
        _read_favicons(resp)
    if "items" in request.args:
        resp, status = _read_items(db_path, resp)
        if status is not None:
            return resp, status
    if "unread_item_ids" in request.args:
        _read_unread_item_ids(db_path, resp)
    if "saved_item_ids" in request.args:
        _read_saved_item_ids(db_path, resp)
    return resp, None


def _handle_mark_item(db_path, mark_id, as_value, resp):
    """处理 mark=item 的写操作。

    as=read 标记已读，as=saved 星标，as=unsaved 取消星标。
    返回 (resp, status)。
    """
    article = store.get_article(db_path, mark_id)
    if article is None:
        return {"error": "文章不存在"}, 404

    if as_value == "read":
        store.set_read(db_path, mark_id, True)
        _read_unread_item_ids(db_path, resp)
    elif as_value == "saved":
        store.set_starred(db_path, mark_id, True)
        _read_saved_item_ids(db_path, resp)
    elif as_value == "unsaved":
        store.set_starred(db_path, mark_id, False)
        _read_saved_item_ids(db_path, resp)
    else:
        return {"error": "as 参数非法"}, 400

    return resp, None


def _handle_mark_feed(db_path, mark_id, as_value, before, resp):
    """处理 mark=feed 的写操作，只支持 as=read。

    before 是 Unix 时间戳，只标记该时间点之前产生的文章。
    """
    if as_value != "read":
        return {"error": "as 参数非法"}, 400

    feed = store.get_feed(db_path, mark_id)
    if feed is None:
        return {"error": "源不存在"}, 404

    now_iso = _now_iso()
    db_module.execute_write(
        db_path,
        "UPDATE articles SET is_read = 1, last_read_at = ? "
        "WHERE feed_id = ? AND "
        "CAST(strftime('%s', COALESCE(NULLIF(published_at, ''), fetched_at)) AS INTEGER) <= ?",
        [now_iso, mark_id, before],
    )
    _read_unread_item_ids(db_path, resp)
    return resp, None


def _handle_mark_group(db_path, mark_id, as_value, before, resp):
    """处理 mark=group 的写操作，只支持 as=read。

    id=0 视为全部源（不加 feed 条件），否则只标记该 folder 下的源。
    """
    if as_value != "read":
        return {"error": "as 参数非法"}, 400

    if mark_id != 0:
        folder = db_module.query_one(
            db_path, "SELECT id FROM folders WHERE id = ?", [mark_id]
        )
        if folder is None:
            return {"error": "分组不存在"}, 404

    now_iso = _now_iso()
    if mark_id == 0:
        db_module.execute_write(
            db_path,
            "UPDATE articles SET is_read = 1, last_read_at = ? "
            "WHERE CAST(strftime('%s', COALESCE(NULLIF(published_at, ''), fetched_at)) AS INTEGER) <= ?",
            [now_iso, before],
        )
    else:
        db_module.execute_write(
            db_path,
            "UPDATE articles SET is_read = 1, last_read_at = ? "
            "WHERE feed_id IN (SELECT id FROM feeds WHERE folder_id = ?) AND "
            "CAST(strftime('%s', COALESCE(NULLIF(published_at, ''), fetched_at)) AS INTEGER) <= ?",
            [now_iso, mark_id, before],
        )
    _read_unread_item_ids(db_path, resp)
    return resp, None


def _handle_mark(db_path, resp):
    """处理 POST form 里的 mark 写操作。返回 (resp, status)。"""
    mark = request.form.get("mark")
    if mark not in ("item", "feed", "group"):
        return {"error": "mark 参数非法"}, 400

    raw_id = request.form.get("id")
    mark_id = _parse_int(raw_id) if raw_id is not None else None
    if mark_id is None:
        return {"error": "id 参数非法"}, 400

    as_value = request.form.get("as")

    if mark == "item":
        return _handle_mark_item(db_path, mark_id, as_value, resp)

    # feed 和 group 只允许 as=read
    if as_value != "read":
        return {"error": "as 参数非法"}, 400

    raw_before = request.form.get("before")
    before = _parse_int(raw_before) if raw_before is not None else None
    if before is None:
        return {"error": "before 参数非法"}, 400

    if mark == "feed":
        return _handle_mark_feed(db_path, mark_id, as_value, before, resp)
    return _handle_mark_group(db_path, mark_id, as_value, before, resp)


def _handle_unread_recently_read(db_path, resp):
    """把最近 24 小时内被标为已读的文章改回未读。"""
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    db_module.execute_write(
        db_path,
        "UPDATE articles SET is_read = 0 "
        "WHERE is_read = 1 AND last_read_at >= ?",
        [cutoff],
    )
    _read_unread_item_ids(db_path, resp)
    return resp, None


@fever_bp.route("/fever", methods=["GET", "POST"], strict_slashes=False)
def fever():
    """Fever API 主入口。

    流程：先鉴权 → 检查有没有 api 参数 → 处理读参数 → 处理写操作 → 合并响应。
    """
    if not _api_key_ok():
        return jsonify({"api_version": 3, "auth": 0})

    if "api" not in request.args:
        return jsonify({"error": "缺少 api 参数"}), 400

    db_path = _db_path()
    resp = {"api_version": 3, "auth": 1}

    resp, status = _handle_read_params(db_path, resp)
    if status is not None:
        return jsonify(resp), status

    if request.method == "POST":
        if "mark" in request.form:
            resp, status = _handle_mark(db_path, resp)
            if status is not None:
                return jsonify(resp), status
        if request.form.get("unread_recently_read") == "1":
            resp, status = _handle_unread_recently_read(db_path, resp)
            if status is not None:
                return jsonify(resp), status

    return jsonify(resp)
