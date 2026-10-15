
# tests/test_fever.py
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from feedflow import create_app, store
from feedflow import db as db_module

API_KEY = "testkey123"


def _make_app(db_path, fever_api_key=API_KEY):
    """建一个 app，返回 (client, db_path)。fever_api_key 传 None 表示不配置。"""
    os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"
    cfg = {
        "db_path": db_path,
        "host": "127.0.0.1",
        "port": 8301,
        "fetch_interval": 30,
        "user_agent": "FeedFlow-test",
    }
    if fever_api_key is not None:
        cfg["fever_api_key"] = fever_api_key
    app = create_app(cfg)
    app.config.update(TESTING=True)
    client = app.test_client()
    return client, db_path


@pytest.fixture
def fever_client(tmp_path):
    """常规 app，带正确 fever_api_key，返回 (client, db_path)。"""
    db_path = str(tmp_path / "fever.db")
    db_module.init_db(db_path)
    client, db_path = _make_app(db_path)
    return client, db_path


@pytest.fixture
def fever_client_no_key(tmp_path):
    """没有配置 fever_api_key 的 app，返回 (client, db_path)。"""
    db_path = str(tmp_path / "fever_nokey.db")
    db_module.init_db(db_path)
    client, db_path = _make_app(db_path, fever_api_key=None)
    return client, db_path


def _seed(db_path, n=3, folder=True, read=0, starred=0):
    """建 1 个分组 + 2 个源（一个在分组内、一个未分组）+ n 篇文章，返回 dict。

    返回 dict：folder_id, feed1, feed2, article_ids
    article_ids 顺序与插入顺序一致（id 递增）。

    先清空 create_app 自动写入的演示数据，保证计数类断言确定。
    """
    for table in ("articles", "feeds", "folders"):
        db_module.execute_write(db_path, f"DELETE FROM {table}")
    if folder:
        folder_id = store.create_folder(db_path, "科技")
    else:
        folder_id = None

    feed1 = db_module.execute_write(
        db_path,
        "INSERT INTO feeds(folder_id, title, site_url, feed_url, description,"
        " interval_min, enabled, position, created_at)"
        " VALUES(?, ?, ?, ?, '', 0, 1, 0, ?)",
        (folder_id, "源一", "http://example.com/1", "http://example.com/1/rss",
         "2026-10-15T00:00:00+00:00"),
    )
    feed2 = db_module.execute_write(
        db_path,
        "INSERT INTO feeds(folder_id, title, site_url, feed_url, description,"
        " interval_min, enabled, position, created_at)"
        " VALUES(?, ?, ?, ?, '', 0, 1, 0, ?)",
        (None, "源二", "http://example.com/2", "http://example.com/2/rss",
         "2026-10-15T00:00:00+00:00"),
    )

    base = datetime(2026, 10, 15, 0, 0, 0, tzinfo=UTC)
    article_ids = []
    for i in range(n):
        # 前一半给 feed1，后一半给 feed2，保证两个源都有文章
        fid = feed1 if i % 2 == 0 else feed2
        published = (base + timedelta(minutes=i)).isoformat()
        aid = store.insert_article(
            db_path,
            fid,
            f"g{i}",
            f"标题{i}",
            f"作者{i}",
            f"http://example.com/a{i}",
            f"摘要{i}",
            f"<p>正文{i}</p>",
            f"正文{i}",
            published,
        )
        article_ids.append(aid)

    for aid in article_ids:
        db_module.execute_write(
            db_path,
            "UPDATE articles SET is_read=?, is_starred=? WHERE id=?",
            (read, starred, aid),
        )

    return {
        "folder_id": folder_id,
        "feed1": feed1,
        "feed2": feed2,
        "article_ids": article_ids,
    }


def _post_api(client, query="api", data=None):
    """POST /fever/ 请求，query 控制是否带 ?api。"""
    url = "/fever/?" + query if query else "/fever/"
    payload = dict(data or {})
    return client.post(url, data=payload)


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------

def test_auth_fail_no_key(fever_client):
    """不带 api_key 请求，auth 应为 0。"""
    client, _ = fever_client
    resp = client.post("/fever/?api", data={"groups": "1"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["auth"] == 0


def test_auth_fail_wrong_key(fever_client):
    """api_key 错误，auth 应为 0。"""
    client, _ = fever_client
    resp = client.post("/fever/?api", data={"api_key": "wrong", "groups": "1"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["auth"] == 0


def test_auth_disabled(fever_client_no_key):
    """没配置 fever_api_key 时，任何请求 auth 都为 0。"""
    client, _ = fever_client_no_key
    resp = client.post("/fever/?api", data={"api_key": "anything", "groups": "1"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["auth"] == 0


def test_missing_api_param(fever_client):
    """带正确 key 但 URL 没有 ?api，应返回 400。"""
    client, _ = fever_client
    resp = client.post("/fever/", data={"api_key": API_KEY, "groups": "1"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# groups / feeds
# ---------------------------------------------------------------------------

def test_groups(fever_client):
    """groups 返回 api_version/auth，分组与未分组源都在 feeds_groups 里。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=2, folder=True)
    resp = client.post("/fever/?api&groups", data={"api_key": API_KEY})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["api_version"] == 3
    assert data["auth"] == 1

    group_ids = [g["id"] for g in data["groups"]]
    assert seed["folder_id"] in group_ids

    fg = {entry["group_id"]: entry["feed_ids"] for entry in data["feeds_groups"]}
    assert str(seed["feed1"]) in fg.get(seed["folder_id"], "")
    # 未分组源出现在 group_id 0
    assert str(seed["feed2"]) in fg.get(0, "")


def test_feeds(fever_client):
    """feeds 列表字段齐全，is_spark 全 0，url 就是 feed_url。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=2, folder=True)
    resp = client.post("/fever/?api&feeds", data={"api_key": API_KEY})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["auth"] == 1
    feeds = data["feeds"]
    assert len(feeds) >= 2

    for f in feeds:
        assert "id" in f
        assert "favicon_id" in f
        assert "title" in f
        assert "url" in f
        assert "site_url" in f
        assert "is_spark" in f
        assert "last_updated_on_time" in f
        assert f["is_spark"] == 0

    by_id = {f["id"]: f for f in feeds}
    assert by_id[seed["feed1"]]["url"] == "http://example.com/1/rss"
    assert by_id[seed["feed2"]]["url"] == "http://example.com/2/rss"


def test_favicons(fever_client):
    """favicons 非空，data 是 data:image 开头的内联图片。"""
    client, db_path = fever_client
    _seed(db_path, n=1, folder=True)
    resp = client.post("/fever/?api&favicons", data={"api_key": API_KEY})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["auth"] == 1
    assert len(data["favicons"]) > 0
    for fav in data["favicons"]:
        assert fav["data"].startswith("data:image")


# ---------------------------------------------------------------------------
# items
# ---------------------------------------------------------------------------

def test_items_default(fever_client):
    """默认返回全部（不超过 50），按 id 降序，字段齐全，total_items 正确。"""
    client, db_path = fever_client
    _seed(db_path, n=5, folder=True)
    resp = client.post("/fever/?api&items", data={"api_key": API_KEY})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["auth"] == 1
    assert data["total_items"] == 5
    items = data["items"]
    assert len(items) == 5

    ids = [it["id"] for it in items]
    assert ids == sorted(ids, reverse=True)

    for it in items:
        assert "id" in it
        assert "feed_id" in it
        assert "title" in it
        assert "author" in it
        assert "html" in it
        assert "url" in it
        assert "is_saved" in it
        assert "is_read" in it
        assert "created_on_time" in it


def test_items_since_id(fever_client):
    """since_id 取最大 id，返回空列表。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=3, folder=True)
    max_id = max(seed["article_ids"])
    resp = client.post(
        f"/fever/?api&items&since_id={max_id}",
        data={"api_key": API_KEY},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["items"] == []


def test_items_max_id(fever_client):
    """max_id 取最小 id 返回空；取最大 id 返回其余且降序。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=3, folder=True)
    ids = seed["article_ids"]
    min_id = min(ids)
    max_id = max(ids)

    resp = client.post(
        f"/fever/?api&items&max_id={min_id}",
        data={"api_key": API_KEY},
    )
    assert resp.status_code == 200
    assert resp.get_json()["items"] == []

    resp = client.post(
        f"/fever/?api&items&max_id={max_id}",
        data={"api_key": API_KEY},
    )
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    ret_ids = [it["id"] for it in items]
    assert max_id not in ret_ids
    assert ret_ids == sorted(ret_ids, reverse=True)


def test_items_with_ids(fever_client):
    """with_ids 精确返回指定的那几篇。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=3, folder=True)
    ids = seed["article_ids"]
    want = [ids[0], ids[2]]
    resp = client.post(
        f"/fever/?api&items&with_ids={want[0]},{want[1]}",
        data={"api_key": API_KEY},
    )
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    got = sorted(it["id"] for it in items)
    assert got == sorted(want)


def test_items_invalid_param(fever_client):
    """since_id 非整数应返回 400。"""
    client, db_path = fever_client
    _seed(db_path, n=1, folder=True)
    resp = client.post(
        "/fever/?api&items&since_id=abc",
        data={"api_key": API_KEY},
    )
    assert resp.status_code == 400


def test_items_limit_50(fever_client):
    """造 60 篇，默认只返回 50 篇。"""
    client, db_path = fever_client
    _seed(db_path, n=60, folder=True)
    resp = client.post("/fever/?api&items", data={"api_key": API_KEY})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) == 50


# ---------------------------------------------------------------------------
# ids
# ---------------------------------------------------------------------------

def test_unread_item_ids(fever_client):
    """全部未读时返回全部 id；标一篇已读后不再包含它。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=5, folder=True, read=0)
    resp = client.post("/fever/?api&unread_item_ids", data={"api_key": API_KEY})
    assert resp.status_code == 200
    data = resp.get_json()
    ids = [int(x) for x in data["unread_item_ids"].split(",") if x]
    assert sorted(ids) == sorted(seed["article_ids"])

    target = seed["article_ids"][0]
    db_module.execute_write(
        db_path, "UPDATE articles SET is_read=1 WHERE id=?", (target,)
    )
    resp = client.post("/fever/?api&unread_item_ids", data={"api_key": API_KEY})
    ids = [int(x) for x in resp.get_json()["unread_item_ids"].split(",") if x]
    assert target not in ids
    assert len(ids) == 4


def test_saved_item_ids(fever_client):
    """星标两篇后返回这两个 id。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=4, folder=True)
    starred = [seed["article_ids"][0], seed["article_ids"][2]]
    for aid in starred:
        db_module.execute_write(
            db_path, "UPDATE articles SET is_starred=1 WHERE id=?", (aid,)
        )
    resp = client.post("/fever/?api&saved_item_ids", data={"api_key": API_KEY})
    assert resp.status_code == 200
    ids = [int(x) for x in resp.get_json()["saved_item_ids"].split(",") if x]
    assert sorted(ids) == sorted(starred)


# ---------------------------------------------------------------------------
# 写操作
# ---------------------------------------------------------------------------

def test_mark_item_read(fever_client):
    """mark=item&as=read 把文章标已读，响应里 unread 不再含它。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=3, folder=True, read=0)
    target = seed["article_ids"][1]
    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "mark": "item",
            "as": "read",
            "id": str(target),
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["auth"] == 1
    article = store.get_article(db_path, target)
    assert article["is_read"] == 1

    unread = [int(x) for x in data["unread_item_ids"].split(",") if x]
    assert target not in unread


def test_mark_item_saved_unsaved(fever_client):
    """as=saved 星标，as=unsaved 取消星标。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=3, folder=True)
    target = seed["article_ids"][0]

    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "mark": "item",
            "as": "saved",
            "id": str(target),
        },
    )
    assert resp.status_code == 200
    assert store.get_article(db_path, target)["is_starred"] == 1
    saved = [int(x) for x in resp.get_json()["saved_item_ids"].split(",") if x]
    assert target in saved

    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "mark": "item",
            "as": "unsaved",
            "id": str(target),
        },
    )
    assert resp.status_code == 200
    assert store.get_article(db_path, target)["is_starred"] == 0
    saved = [int(x) for x in resp.get_json()["saved_item_ids"].split(",") if x]
    assert target not in saved


def test_mark_feed_read(fever_client):
    """mark=feed&as=read&before=今天，把 feed1 昨天的文章全标已读，feed2 不动。"""
    client, db_path = fever_client
    folder_id = store.create_folder(db_path, "科技")
    feed1 = db_module.execute_write(
        db_path,
        "INSERT INTO feeds(folder_id, title, site_url, feed_url, description,"
        " interval_min, enabled, position, created_at)"
        " VALUES(?, ?, ?, ?, '', 0, 1, 0, ?)",
        (folder_id, "源一", "http://example.com/1", "http://example.com/1/rss",
         "2026-10-15T00:00:00+00:00"),
    )
    feed2 = db_module.execute_write(
        db_path,
        "INSERT INTO feeds(folder_id, title, site_url, feed_url, description,"
        " interval_min, enabled, position, created_at)"
        " VALUES(?, ?, ?, ?, '', 0, 1, 0, ?)",
        (None, "源二", "http://example.com/2", "http://example.com/2/rss",
         "2026-10-15T00:00:00+00:00"),
    )
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    f1_ids = []
    for i in range(3):
        f1_ids.append(
            store.insert_article(
                db_path, feed1, f"f1g{i}", f"F1-{i}", "a", f"http://e/1/{i}",
                "s", "<p>x</p>", "x", yesterday,
            )
        )
    f2_id = store.insert_article(
        db_path, feed2, "f2g0", "F2-0", "a", "http://e/2/0",
        "s", "<p>y</p>", "y", yesterday,
    )

    before = int(datetime.now(UTC).timestamp())
    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "mark": "feed",
            "as": "read",
            "id": str(feed1),
            "before": str(before),
        },
    )
    assert resp.status_code == 200
    for aid in f1_ids:
        assert store.get_article(db_path, aid)["is_read"] == 1
    assert store.get_article(db_path, f2_id)["is_read"] == 0


def test_mark_group_read(fever_client):
    """mark=group&as=read&before=明天，组内源全已读，未分组源未读。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=4, folder=True, read=0)
    tomorrow = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "mark": "group",
            "as": "read",
            "id": str(seed["folder_id"]),
            "before": str(tomorrow),
        },
    )
    assert resp.status_code == 200

    # 找出哪些文章属于 feed1（组内）
    for aid in seed["article_ids"]:
        art = store.get_article(db_path, aid)
        if art["feed_id"] == seed["feed1"]:
            assert art["is_read"] == 1
        else:
            assert art["is_read"] == 0


def test_mark_group_zero(fever_client):
    """mark=group&as=read&id=0&before=明天，全部文章变已读。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=4, folder=True, read=0)
    tomorrow = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "mark": "group",
            "as": "read",
            "id": "0",
            "before": str(tomorrow),
        },
    )
    assert resp.status_code == 200
    for aid in seed["article_ids"]:
        assert store.get_article(db_path, aid)["is_read"] == 1


def test_unread_recently_read(fever_client):
    """unread_recently_read=1 把最近标已读的 2 篇变回未读。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=3, folder=True, read=0)
    targets = [seed["article_ids"][0], seed["article_ids"][1]]
    for aid in targets:
        store.set_read(db_path, aid, 1)

    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "unread_recently_read": "1",
        },
    )
    assert resp.status_code == 200
    for aid in targets:
        assert store.get_article(db_path, aid)["is_read"] == 0


def test_mark_invalid(fever_client):
    """各种非法参数应返回 400 或 404。"""
    client, db_path = fever_client
    seed = _seed(db_path, n=2, folder=True)

    resp = client.post(
        "/fever/?api",
        data={"api_key": API_KEY, "mark": "bogus"},
    )
    assert resp.status_code == 400

    resp = client.post(
        "/fever/?api",
        data={"api_key": API_KEY, "mark": "item", "as": "read"},
    )
    assert resp.status_code == 400

    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "mark": "feed",
            "as": "read",
            "id": str(seed["feed1"]),
        },
    )
    assert resp.status_code == 400

    resp = client.post(
        "/fever/?api",
        data={
            "api_key": API_KEY,
            "mark": "item",
            "as": "read",
            "id": "99999",
        },
    )
    assert resp.status_code == 404
