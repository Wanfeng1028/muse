# tests/test_fever_deep2.py
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"

from feedflow import create_app, store
from feedflow import db as db_module


def _make_app(tmp_path, api_key="test-fever-key"):
    db_path = str(tmp_path / "feedflow.db")
    os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"
    app = create_app({
        "db_path": db_path,
        "host": "127.0.0.1",
        "port": 8302,
        "fetch_interval": 30,
        "user_agent": "FeedFlow-test",
        "fever_api_key": api_key,
    })
    app.config["TESTING"] = True
    _clean_seed(db_path)
    return app, db_path


def _clean_seed(db_path):
    """清掉 create_app 自动写入的演示数据，保证计数类断言确定。"""
    for table in ("articles", "feeds", "folders"):
        db_module.execute_write(db_path, f"DELETE FROM {table}")


def _seed_feed(db_path, feed_url, title, folder_id=None):
    fid = store.create_feed(db_path, feed_url, folder_id=folder_id)
    store.update_feed(db_path, fid, title=title)
    return fid


def _seed_article(db_path, feed_id, title, published_at=None, is_read=0, is_starred=0):
    aid = store.insert_article(
        db_path,
        feed_id,
        guid=f"guid-{title}",
        title=title,
        author="",
        link=f"https://example.com/{title}",
        summary=f"summary-{title}",
        content_html=f"<p>{title}</p>",
        content_text=title,
        published_at=published_at or "2024-01-01T00:00:00+00:00",
    )
    if is_read:
        store.set_read(db_path, aid, True)
    if is_starred:
        store.set_starred(db_path, aid, True)
    return aid


# 1. 未配置 fever_api_key 时，任意读参数都返回 auth=0，且是合法 JSON
def test_auth_disabled_when_no_key(tmp_path):
    app, _ = _make_app(tmp_path, api_key=None)
    client = app.test_client()
    rv = client.get("/fever/?api&groups&feeds&items")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["auth"] == 0
    assert data["api_version"] == 3


# 2. api_key 错误、缺失、空字符串都返回 auth=0，且响应结构一致不泄露配置
def test_auth_failure_variants(tmp_path):
    app, _ = _make_app(tmp_path, api_key="test-fever-key")
    client = app.test_client()

    rv_missing = client.get("/fever/?api&groups")
    assert rv_missing.status_code == 200
    d_missing = rv_missing.get_json()
    assert d_missing["auth"] == 0
    assert d_missing["api_version"] == 3

    rv_wrong = client.post("/fever/?api&groups", data={"api_key": "wrong-key"})
    assert rv_wrong.status_code == 200
    d_wrong = rv_wrong.get_json()
    assert d_wrong["auth"] == 0
    assert d_wrong["api_version"] == 3

    rv_empty = client.post("/fever/?api&groups", data={"api_key": ""})
    assert rv_empty.status_code == 200
    d_empty = rv_empty.get_json()
    assert d_empty["auth"] == 0

    assert d_missing == d_wrong == d_empty


# 3. 组合读参数 groups+feeds+items+unread_item_ids 一次返回，键齐全且数据一致
def test_combined_read_params(tmp_path):
    app, db_path = _make_app(tmp_path)
    folder_id = store.create_folder(db_path, "技术")
    fid = _seed_feed(db_path, "https://a.example/rss", "Feed A", folder_id=folder_id)
    a1 = _seed_article(db_path, fid, "art-1", is_read=0)
    a2 = _seed_article(db_path, fid, "art-2", is_read=1)

    client = app.test_client()
    rv = client.get(
    "/fever/?api&groups&feeds&items&unread_item_ids&"
    + urlencode({"api_key": "test-fever-key"}),
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["auth"] == 1
    assert data["api_version"] == 3
    for key in ("groups", "feeds", "items", "unread_item_ids", "feeds_groups"):
        assert key in data

    assert len(data["groups"]) == 1
    assert data["groups"][0]["id"] == folder_id
    assert data["groups"][0]["title"] == "技术"

    assert len(data["feeds"]) == 1
    assert data["feeds"][0]["id"] == fid

    item_ids = {it["id"] for it in data["items"]}
    assert a1 in item_ids
    assert a2 in item_ids

    unread_ids = data["unread_item_ids"].split(",") if data["unread_item_ids"] else []
    assert str(a1) in unread_ids
    assert str(a2) not in unread_ids


# 4. mark=feed&as=read&id=<feed_id> 只标该源已读，另一个源的未读不受影响
def test_mark_feed_read_only_that_feed(tmp_path):
    app, db_path = _make_app(tmp_path)
    f1 = _seed_feed(db_path, "https://f1.example/rss", "F1")
    f2 = _seed_feed(db_path, "https://f2.example/rss", "F2")
    a1 = _seed_article(db_path, f1, "f1-art", published_at="2020-01-01T00:00:00+00:00")
    a2 = _seed_article(db_path, f2, "f2-art", published_at="2020-01-01T00:00:00+00:00")

    client = app.test_client()
    rv = client.post(
        "/fever/?api",
        data={
            "api_key": "test-fever-key",
            "mark": "feed",
            "as": "read",
            "id": str(f1),
            "before": "9999999999",
        },
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["auth"] == 1

    row1 = store.get_article(db_path, a1)
    row2 = store.get_article(db_path, a2)
    assert row1["is_read"] == 1
    assert row2["is_read"] == 0

    unread_ids = data["unread_item_ids"].split(",") if data["unread_item_ids"] else []
    assert str(a1) not in unread_ids
    assert str(a2) in unread_ids


# 5. mark=group&as=read&id=0 标记全部源已读，未分组源也算
def test_mark_group_zero_marks_all(tmp_path):
    app, db_path = _make_app(tmp_path)
    folder_id = store.create_folder(db_path, "组A")
    f_grouped = _seed_feed(db_path, "https://g.example/rss", "G", folder_id=folder_id)
    f_ungrouped = _seed_feed(db_path, "https://u.example/rss", "U")
    a1 = _seed_article(db_path, f_grouped, "g-art", published_at="2020-01-01T00:00:00+00:00")
    a2 = _seed_article(db_path, f_ungrouped, "u-art", published_at="2020-01-01T00:00:00+00:00")

    client = app.test_client()
    rv = client.post(
        "/fever/?api",
        data={
            "api_key": "test-fever-key",
            "mark": "group",
            "as": "read",
            "id": "0",
            "before": "9999999999",
        },
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["auth"] == 1
    assert data["unread_item_ids"] == ""

    assert store.get_article(db_path, a1)["is_read"] == 1
    assert store.get_article(db_path, a2)["is_read"] == 1


# 6. items 分页边界：since_id 严格大于、max_id 严格小于；with_ids 精确返回
def test_items_pagination_boundaries(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _seed_feed(db_path, "https://p.example/rss", "P")
    ids = [_seed_article(db_path, fid, f"p-{i}") for i in range(5)]

    client = app.test_client()

    # since_id 恰好等于边界 id：应严格大于，不包含边界
    rv_since = client.get(
    "/fever/?api&items&"
    + urlencode({"api_key": "test-fever-key", "since_id": str(ids[1])}),
    )
    data_since = rv_since.get_json()
    got_since = [it["id"] for it in data_since["items"]]
    assert ids[1] not in got_since
    for x in ids[2:]:
        assert x in got_since

    # max_id 恰好等于边界 id：应严格小于，不包含边界
    rv_max = client.get(
    "/fever/?api&items&"
    + urlencode({"api_key": "test-fever-key", "max_id": str(ids[3])}),
    )
    data_max = rv_max.get_json()
    got_max = [it["id"] for it in data_max["items"]]
    assert ids[3] not in got_max
    for x in ids[:3]:
        assert x in got_max

    # with_ids 精确返回指定的 id 集合
    rv_with = client.get(
        "/fever/?api&items&"
        + urlencode({
            "api_key": "test-fever-key",
            "with_ids": f"{ids[0]},{ids[2]},{ids[4]}",
        }),
    )
    data_with = rv_with.get_json()
    got_with = sorted(it["id"] for it in data_with["items"])
    assert got_with == sorted([ids[0], ids[2], ids[4]])


# 7. items 默认 50 封顶：造 60 篇，不带分页参数只返回 50 篇
def test_items_default_limit_50(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _seed_feed(db_path, "https://many.example/rss", "Many")
    for i in range(60):
        _seed_article(db_path, fid, f"many-{i}")

    client = app.test_client()
    rv = client.get(
    "/fever/?api&items&"
    + urlencode({"api_key": "test-fever-key"}),
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["items"]) == 50
    assert data["total_items"] == 60


# 8. unread_recently_read：标已读后调用，该文章回到未读列表
def test_unread_recently_read(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _seed_feed(db_path, "https://rr.example/rss", "RR")
    a1 = _seed_article(db_path, fid, "rr-1")
    a2 = _seed_article(db_path, fid, "rr-2")

    client = app.test_client()
    rv_mark = client.post(
        "/fever/?api",
        data={
            "api_key": "test-fever-key",
            "mark": "item",
            "as": "read",
            "id": str(a1),
        },
    )
    assert rv_mark.status_code == 200
    assert store.get_article(db_path, a1)["is_read"] == 1

    rv_rr = client.post(
        "/fever/?api",
        data={"api_key": "test-fever-key", "unread_recently_read": "1"},
    )
    assert rv_rr.status_code == 200
    data = rv_rr.get_json()
    unread_ids = data["unread_item_ids"].split(",") if data["unread_item_ids"] else []
    assert str(a1) in unread_ids
    assert str(a2) in unread_ids
    assert store.get_article(db_path, a1)["is_read"] == 0


# 9. favicons 返回占位 data URI，以 data:image/gif;base64 开头
def test_favicons_placeholder(tmp_path):
    app, _ = _make_app(tmp_path)
    client = app.test_client()
    rv = client.get(
    "/fever/?api&favicons&"
    + urlencode({"api_key": "test-fever-key"}),
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert "favicons" in data
    assert len(data["favicons"]) == 1
    fav = data["favicons"][0]
    assert fav["id"] == 1
    assert fav["data"].startswith("data:image/gif;base64,")


# 10. feeds 里每项 is_spark 恒为 0
def test_feeds_is_spark_zero(tmp_path):
    app, db_path = _make_app(tmp_path)
    _seed_feed(db_path, "https://s1.example/rss", "S1")
    _seed_feed(db_path, "https://s2.example/rss", "S2")

    client = app.test_client()
    rv = client.get(
    "/fever/?api&feeds&"
    + urlencode({"api_key": "test-fever-key"}),
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["feeds"]) == 2
    for f in data["feeds"]:
        assert f["is_spark"] == 0


# 11. 非法 mark 参数（mark=nope）返回 400，不抛 500
def test_invalid_mark_returns_400(tmp_path):
    app, _ = _make_app(tmp_path)
    client = app.test_client()
    rv = client.post(
        "/fever/?api",
        data={"api_key": "test-fever-key", "mark": "nope", "id": "1"},
    )
    assert rv.status_code == 400
    data = rv.get_json()
    assert "error" in data

    # 非法 as（feed 场景）也返回 400
    rv2 = client.post(
        "/fever/?api",
        data={
            "api_key": "test-fever-key",
            "mark": "feed",
            "as": "saved",
            "id": "1",
            "before": "9999999999",
        },
    )
    assert rv2.status_code == 400
    assert "error" in rv2.get_json()

    # id 非法也返回 400
    rv3 = client.post(
        "/fever/?api",
        data={"api_key": "test-fever-key", "mark": "item", "as": "read", "id": "abc"},
    )
    assert rv3.status_code == 400


# 12. POST form 传 api_key 与 query string 传 api_key 两种方式都通过鉴权
def test_api_key_via_form_and_query(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _seed_feed(db_path, "https://k.example/rss", "K")
    _seed_article(db_path, fid, "k-art")

    client = app.test_client()

    rv_form = client.post(
        "/fever/?api&groups",
        data={"api_key": "test-fever-key"},
    )
    assert rv_form.status_code == 200
    d_form = rv_form.get_json()
    assert d_form["auth"] == 1
    assert "groups" in d_form

    rv_query = client.get(
    "/fever/?api&groups&"
    + urlencode({"api_key": "test-fever-key"}),
    )
    assert rv_query.status_code == 200
    d_query = rv_query.get_json()
    assert d_query["auth"] == 1
    assert "groups" in d_query


# 补充 13. 缺少 api 参数时返回 400（已通过鉴权的情况下）
def test_missing_api_param_returns_400(tmp_path):
    app, _ = _make_app(tmp_path)
    client = app.test_client()
    rv = client.post("/fever/", data={"api_key": "test-fever-key"})
    assert rv.status_code == 400
    data = rv.get_json()
    assert "error" in data


# 补充 14. items with_ids 为空串或含非法值时返回 400
def test_items_with_ids_invalid(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _seed_feed(db_path, "https://wi.example/rss", "WI")
    _seed_article(db_path, fid, "wi-1")

    client = app.test_client()

    rv_empty = client.get(
    "/fever/?api&items&"
    + urlencode({"api_key": "test-fever-key", "with_ids": "  "}),
    )
    assert rv_empty.status_code == 400

    rv_bad = client.get(
    "/fever/?api&items&"
    + urlencode({"api_key": "test-fever-key", "with_ids": "abc"}),
    )
    assert rv_bad.status_code == 400


# 补充 15. mark=item as=saved / unsaved 星标切换，saved_item_ids 一致
def test_mark_item_saved_and_unsaved(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _seed_feed(db_path, "https://sv.example/rss", "SV")
    a1 = _seed_article(db_path, fid, "sv-1")

    client = app.test_client()

    rv_save = client.post(
        "/fever/?api",
        data={
            "api_key": "test-fever-key",
            "mark": "item",
            "as": "saved",
            "id": str(a1),
        },
    )
    assert rv_save.status_code == 200
    d_save = rv_save.get_json()
    assert store.get_article(db_path, a1)["is_starred"] == 1
    saved_ids = d_save["saved_item_ids"].split(",") if d_save["saved_item_ids"] else []
    assert str(a1) in saved_ids

    rv_unsave = client.post(
        "/fever/?api",
        data={
            "api_key": "test-fever-key",
            "mark": "item",
            "as": "unsaved",
            "id": str(a1),
        },
    )
    assert rv_unsave.status_code == 200
    d_unsave = rv_unsave.get_json()
    assert store.get_article(db_path, a1)["is_starred"] == 0
    assert d_unsave["saved_item_ids"] == ""


# 补充 16. mark=item 不存在文章返回 404
def test_mark_item_missing_returns_404(tmp_path):
    app, _ = _make_app(tmp_path)
    client = app.test_client()
    rv = client.post(
        "/fever/?api",
        data={
            "api_key": "test-fever-key",
            "mark": "item",
            "as": "read",
            "id": "99999",
        },
    )
    assert rv.status_code == 404
    assert "error" in rv.get_json()


# 补充 17. mark=group 不存在分组返回 404
def test_mark_group_missing_returns_404(tmp_path):
    app, _ = _make_app(tmp_path)
    client = app.test_client()
    rv = client.post(
        "/fever/?api",
        data={
            "api_key": "test-fever-key",
            "mark": "group",
            "as": "read",
            "id": "12345",
            "before": "9999999999",
        },
    )
    assert rv.status_code == 404
    assert "error" in rv.get_json()


# 补充 18. feeds_groups 结构：分组内 feed_ids 升序、未分组归入 group 0
def test_feeds_groups_structure(tmp_path):
    app, db_path = _make_app(tmp_path)
    folder_id = store.create_folder(db_path, "组X")
    f1 = _seed_feed(db_path, "https://x1.example/rss", "X1", folder_id=folder_id)
    f2 = _seed_feed(db_path, "https://x2.example/rss", "X2", folder_id=folder_id)
    f3 = _seed_feed(db_path, "https://x3.example/rss", "X3")

    client = app.test_client()
    rv = client.get(
    "/fever/?api&groups&"
    + urlencode({"api_key": "test-fever-key"}),
    )
    assert rv.status_code == 200
    data = rv.get_json()
    groups = data["feeds_groups"]
    assert len(groups) == 2

    g_map = {g["group_id"]: g["feed_ids"] for g in groups}
    assert g_map[folder_id] == ",".join(str(i) for i in sorted([f1, f2]))
    assert g_map[0] == str(f3)
