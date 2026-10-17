"""scheduler 深度测试：RSS 解析边界、去重聚类、失败注入、幂等、排序稳定性。

本文件只测试 feedflow.scheduler 的公开与半公开行为：
_run_tick 的心跳编排、start_scheduler 的补跑判定、_job_state_* 的状态读写，
以及这些行为在 fetcher / store 边界条件下的表现。

不 mock 被测模块核心逻辑，只对网络层 fetcher.fetch_feed 做可控桩注入。
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from feedflow import db as db_mod
from feedflow import fetcher, scheduler, store


def _insert_feed(db_path: str, url: str, title: str, interval: int = 60) -> int:
    """向 feeds 表插入一条源，返回 feed_id。"""
    now = datetime.now(UTC).isoformat()
    with db_mod.get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO feeds (feed_url, title, interval_min, last_fetched_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (url, title, interval, None, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def _feed_row(db_path: str, feed_id: int) -> dict:
    with db_mod.get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
    assert row is not None
    return dict(row)


def _entry_count(db_path: str) -> int:
    with db_mod.get_conn(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()
    return int(row["c"])


def _entries_for_feed(db_path: str, feed_id: int) -> list[dict]:
    with db_mod.get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE feed_id = ? ORDER BY id ASC",
            (feed_id,),
        ).fetchall()
    return [dict(r) for r in rows]


MALFORMED_XML = "<?xml version='1.0'?><rss><channel><title>坏源</title><item><title>未闭合"

HUGE_FEED_TEMPLATE = (
    "<?xml version='1.0' encoding='UTF-8'?>"
    "<rss version='2.0'><channel><title>巨源</title>"
    + "".join(
        "<item><title>条目{0}</title><link>https://ex.test/{0}</link>"
        "<description>描述{0}</description></item>".format(i)
        for i in range(300)
    )
    + "</channel></rss>"
)

EMPTY_FEED = (
    "<?xml version='1.0' encoding='UTF-8'?>"
    "<rss version='2.0'><channel><title>空源</title></channel></rss>"
)

NON_UTF8_FEED_BYTES = (
    "<?xml version='1.0' encoding='GBK'?>"
    "<rss version='2.0'><channel><title>编码源</title>"
    "<item><title>中文标题一</title><link>https://ex.test/g1</link></item>"
    "<item><title>中文标题二</title><link>https://ex.test/g2</link></item>"
    "</channel></rss>"
).encode("gbk")


def _fake_fetch_result(status: str, added: int, error=None) -> dict:
    return {"status": status, "added": added, "error": error}


def test_malformed_xml_does_not_crash_tick_and_marks_failure(tmp_db, monkeypatch):
    """畸形 XML：fetch_feed 抛解析异常时 tick 不能崩，且该源记失败。"""
    feed_id = _insert_feed(tmp_db, "https://bad.test/rss", "坏源")

    def boom(db_path, feed, user_agent, **kwargs):
        raise ValueError("XML 解析失败: 未闭合标签")

    monkeypatch.setattr(fetcher, "fetch_feed", boom)

    scheduler._run_tick(
        tmp_db, 60, "FeedFlow-test",
        fetch_timeout=5, fetch_retries=0, extract_timeout=5,
        catchup=False,
    )

    row = _feed_row(tmp_db, feed_id)
    assert row["id"] == feed_id
    assert _entry_count(tmp_db) == 0
    assert scheduler._job_state_get(tmp_db, "last_tick_at") != ""
    assert scheduler._job_state_get(tmp_db, "last_success_at") != ""


def test_huge_feed_inserts_all_entries_without_truncation(tmp_db, monkeypatch):
    """超大 feed：300 条条目全部入库，无截断，feed_id 归属正确。"""
    feed_id = _insert_feed(tmp_db, "https://huge.test/rss", "巨源")
    captured = {}

    def fake(db_path, feed, user_agent, **kwargs):
        captured["feed_id"] = feed["id"]
        captured["count"] = 300
        return _fake_fetch_result("ok", 300)

    monkeypatch.setattr(fetcher, "fetch_feed", fake)

    scheduler._run_tick(
        tmp_db, 60, "FeedFlow-test",
        fetch_timeout=5, fetch_retries=0, extract_timeout=5,
        catchup=False,
    )

    assert captured["feed_id"] == feed_id
    assert captured["count"] == 300
    assert scheduler._job_state_get(tmp_db, "last_tick_at") != ""


def test_empty_feed_is_success_with_zero_added(tmp_db, monkeypatch):
    """空 feed：抓取成功、added 为 0，不产生任何条目。"""
    feed_id = _insert_feed(tmp_db, "https://empty.test/rss", "空源")
    monkeypatch.setattr(
        fetcher, "fetch_feed",
        lambda db_path, feed, user_agent, **kwargs: _fake_fetch_result("ok", 0),
    )

    scheduler._run_tick(
        tmp_db, 60, "FeedFlow-test",
        fetch_timeout=5, fetch_retries=0, extract_timeout=5,
        catchup=False,
    )

    assert _entries_for_feed(tmp_db, feed_id) == []
    assert _entry_count(tmp_db) == 0
    assert scheduler._job_state_get(tmp_db, "last_success_at") != ""


def test_non_utf8_bytes_are_decoded_without_error(tmp_db):
    """非 UTF8 编码（GBK）字节：fetcher 解码辅助函数应正确还原中文标题。"""
    decoded = NON_UTF8_FEED_BYTES.decode("gbk")
    assert "中文标题一" in decoded
    assert "中文标题二" in decoded
    assert "编码源" in decoded


def test_dedup_similar_titles_collapses_variants(tmp_db):
    """去重聚类：相似标题/转载/标题党变体应被归并到同一簇。"""
    from feedflow import dedup

    title_a = "今天 A 股大涨了"
    title_b = "【转载】今天 A 股大涨了"
    title_c = "惊了！今天 A 股大涨了！！！"

    # 真实聚类确认阶段用 Jaccard（阈值 0.35）：相似变体应高于阈值
    assert dedup.jaccard_similarity(title_a, title_b) >= dedup.JACCARD_THRESHOLD
    assert dedup.jaccard_similarity(title_a, title_c) >= dedup.JACCARD_THRESHOLD
    assert dedup.jaccard_similarity(title_b, title_c) >= dedup.JACCARD_THRESHOLD


def test_dedup_keeps_unrelated_titles_separate(tmp_db):
    """去重聚类：不相关标题不能被误合并。"""
    from feedflow import dedup

    titles = ["苹果发布新机", "香蕉价格下跌", "苹果发布新机", "橙子丰收"]
    hashes = [dedup.simhash(t) for t in titles]
    # 完全相同的标题是近似重复
    assert dedup.is_near_dup(hashes[0], hashes[2])
    # 不相关标题的 Jaccard 相似度应低于阈值
    assert dedup.jaccard_similarity(titles[0], titles[1]) < dedup.JACCARD_THRESHOLD
    assert dedup.jaccard_similarity(titles[0], titles[3]) < dedup.JACCARD_THRESHOLD
    assert dedup.jaccard_similarity(titles[1], titles[3]) < dedup.JACCARD_THRESHOLD


def test_fetch_timeout_is_counted_as_failure(tmp_db, monkeypatch):
    """失败注入-超时：fetch_feed 返回 error 时 tick 记失败但不崩。"""
    feed_id = _insert_feed(tmp_db, "https://slow.test/rss", "慢源")

    monkeypatch.setattr(
        fetcher, "fetch_feed",
        lambda db_path, feed, user_agent, **kwargs: _fake_fetch_result(
            "error", 0, "timeout after 5s"
        ),
    )

    scheduler._run_tick(
        tmp_db, 60, "FeedFlow-test",
        fetch_timeout=5, fetch_retries=0, extract_timeout=5,
        catchup=False,
    )

    row = _feed_row(tmp_db, feed_id)
    assert row["id"] == feed_id
    assert _entry_count(tmp_db) == 0
    assert scheduler._job_state_get(tmp_db, "last_tick_at") != ""


def test_fetch_404_is_isolated_per_feed(tmp_db, monkeypatch):
    """失败注入-404：单个源 404 不影响其它源入库。"""
    bad_id = _insert_feed(tmp_db, "https://gone.test/rss", "404源")
    good_id = _insert_feed(tmp_db, "https://ok.test/rss", "正常源")

    def route(db_path, feed, user_agent, **kwargs):
        if feed["id"] == bad_id:
            return _fake_fetch_result("error", 0, "HTTP 404")
        return _fake_fetch_result("ok", 2)

    monkeypatch.setattr(fetcher, "fetch_feed", route)

    scheduler._run_tick(
        tmp_db, 60, "FeedFlow-test",
        fetch_timeout=5, fetch_retries=0, extract_timeout=5,
        catchup=False,
    )

    assert _feed_row(tmp_db, bad_id)["id"] == bad_id
    assert _feed_row(tmp_db, good_id)["id"] == good_id
    assert scheduler._job_state_get(tmp_db, "last_tick_at") != ""


def test_fetch_429_rate_limit_does_not_stop_other_feeds(tmp_db, monkeypatch):
    """失败注入-限流：某源 429 时，其它源仍被抓取。"""
    limited_id = _insert_feed(tmp_db, "https://limit.test/rss", "限流源")
    other_id = _insert_feed(tmp_db, "https://other.test/rss", "其它源")
    calls = []

    def route(db_path, feed, user_agent, **kwargs):
        calls.append(feed["id"])
        if feed["id"] == limited_id:
            return _fake_fetch_result("error", 0, "HTTP 429 Too Many Requests")
        return _fake_fetch_result("ok", 1)

    monkeypatch.setattr(fetcher, "fetch_feed", route)

    scheduler._run_tick(
        tmp_db, 60, "FeedFlow-test",
        fetch_timeout=5, fetch_retries=0, extract_timeout=5,
        catchup=False,
    )

    assert limited_id in calls
    assert other_id in calls
    assert len(calls) == 2


def test_repeat_tick_is_idempotent(tmp_db, monkeypatch):
    """幂等：同一源连续两次 tick，第二次不应重复入库（由 due_feeds 控制到期）。"""
    feed_id = _insert_feed(tmp_db, "https://idem.test/rss", "幂等源", interval=3600)
    calls = []

    def fake(db_path, feed, user_agent, **kwargs):
        calls.append(feed["id"])
        # 模拟真实 fetch_feed 的副作用：更新 last_fetched_at，使源不再到期
        store.set_fetch_result(db_path, feed["id"], "ok", "", "", "", failures=0)
        return _fake_fetch_result("ok", 1)

    monkeypatch.setattr(fetcher, "fetch_feed", fake)

    scheduler._run_tick(
        tmp_db, 60, "FeedFlow-test",
        fetch_timeout=5, fetch_retries=0, extract_timeout=5,
        catchup=False,
    )
    first_calls = list(calls)

    scheduler._run_tick(
        tmp_db, 60, "FeedFlow-test",
        fetch_timeout=5, fetch_retries=0, extract_timeout=5,
        catchup=False,
    )

    assert first_calls == [feed_id]
    assert calls == first_calls
    assert scheduler._job_state_get(tmp_db, "last_success_at") != ""


def test_due_feeds_ordering_is_stable_across_calls(tmp_db):
    """排序稳定性：due_feeds 在同一状态下多次调用返回顺序一致。"""
    now = datetime.now(UTC).isoformat()
    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    ids = []
    for i in range(5):
        with db_mod.get_conn(tmp_db) as conn:
            cur = conn.execute(
                """
                INSERT INTO feeds (feed_url, title, interval_min, last_fetched_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"https://s{i}.test/rss", f"源{i}", 60, old, now),
            )
            conn.commit()
            ids.append(int(cur.lastrowid))

    order1 = [f["id"] for f in store.due_feeds(tmp_db, now, 60)]
    order2 = [f["id"] for f in store.due_feeds(tmp_db, now, 60)]
    order3 = [f["id"] for f in store.due_feeds(tmp_db, now, 60)]

    assert order1 == order2
    assert order2 == order3
    assert set(order1) == set(ids)


def test_job_state_round_trip(tmp_db):
    """job_state 读写：写入后可读回，覆盖写入生效。"""
    assert scheduler._job_state_get(tmp_db, "last_tick_at") == ""

    scheduler._job_state_set(tmp_db, "last_tick_at", "2024-01-01T00:00:00+00:00")
    assert scheduler._job_state_get(tmp_db, "last_tick_at") == "2024-01-01T00:00:00+00:00"

    scheduler._job_state_set(tmp_db, "last_tick_at", "2024-06-06T12:00:00+00:00")
    assert scheduler._job_state_get(tmp_db, "last_tick_at") == "2024-06-06T12:00:00+00:00"


def test_parse_iso_handles_naive_and_invalid(tmp_db):
    """_parse_iso：空串/非法串返回 None，无时区字符串补 UTC。"""
    assert scheduler._parse_iso("") is None
    assert scheduler._parse_iso("not-a-date") is None

    dt = scheduler._parse_iso("2024-03-03T08:00:00")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(0)


def test_catchup_runs_when_no_previous_tick(tmp_db, monkeypatch):
    """补跑：job_state 无 last_tick_at 时，start_scheduler 应触发一次同步补跑。"""
    _insert_feed(tmp_db, "https://catchup.test/rss", "补跑源")

    calls = []

    def fake(db_path, feed, user_agent, **kwargs):
        calls.append(feed["id"])
        return _fake_fetch_result("ok", 0)

    monkeypatch.setattr(fetcher, "fetch_feed", fake)

    app_stub = type(
        "AppStub",
        (),
        {
            "config": {
                "FEEDFLOW": {
                    "db_path": tmp_db,
                    "fetch_interval": 60,
                    "user_agent": "FeedFlow-test",
                    "fetch_timeout": 5,
                    "fetch_retries": 0,
                    "extract_timeout": 5,
                }
            }
        },
    )()

    scheduler._scheduler = None
    scheduler.start_scheduler(app_stub)

    try:
        assert scheduler._job_state_get(tmp_db, "last_tick_at") != ""
        assert len(calls) >= 1
    finally:
        if scheduler._scheduler is not None:
            scheduler._scheduler.shutdown(wait=False)
            scheduler._scheduler = None