from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from feedflow import db, scheduler


@pytest.fixture
def tmp_db(tmp_path):
    path = tmp_path / "feedflow.db"
    db.init_db(str(path))
    return str(path)


def _insert_feed(
    db_path: str,
    *,
    title: str = "feed",
    feed_url: str = "https://example.com/feed.xml",
    interval_min: int = 60,
    last_fetched_at: str | None = None,
) -> None:
    db.execute_write(
        db_path,
        "INSERT INTO feeds (folder_id, title, site_url, feed_url, description, "
        "interval_min, enabled, position, created_at, last_fetched_at) "
        "VALUES (NULL, ?, ?, ?, '', ?, 1, 0, ?, ?)",
        (
            title,
            "https://example.com",
            feed_url,
            interval_min,
            db.utcnow(),
            last_fetched_at,
        ),
    )


def _old_iso(seconds: int = 3600) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def test_utcnow_iso_parseable():
    value = scheduler._utcnow_iso()
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None


def test_parse_iso_naive_treated_as_utc():
    parsed = scheduler._parse_iso("2026-01-01T00:00:00")
    assert parsed is not None
    assert parsed.tzinfo == UTC
    assert scheduler._parse_iso("bad") is None
    assert scheduler._parse_iso("") is None


def test_job_state_roundtrip_and_missing(tmp_db):
    scheduler._job_state_set(tmp_db, "alpha", "beta")
    assert scheduler._job_state_get(tmp_db, "alpha") == "beta"
    assert scheduler._job_state_get(tmp_db, "does_not_exist") == ""


def test_run_tick_writes_tick_states(tmp_db, monkeypatch):
    _insert_feed(tmp_db, last_fetched_at=_old_iso(7200))

    calls: list[dict] = []

    def fake_fetch(db_path, feed, user_agent, **kwargs):
        calls.append({"db_path": db_path, "feed": feed, "user_agent": user_agent, **kwargs})
        return {"status": "ok", "added": 2, "error": ""}

    monkeypatch.setattr(scheduler.fetcher, "fetch_feed", fake_fetch)

    scheduler._run_tick(tmp_db, 3600, "ua", 10, 3, 20)

    last_tick = scheduler._job_state_get(tmp_db, "last_tick_at")
    last_success = scheduler._job_state_get(tmp_db, "last_success_at")
    assert last_tick != ""
    assert datetime.fromisoformat(last_tick).tzinfo is not None
    assert last_success != ""
    assert len(calls) == 1


def test_run_tick_forwards_config_args(tmp_db, monkeypatch):
    _insert_feed(tmp_db, last_fetched_at=_old_iso(7200))

    captured: dict = {}

    def fake_fetch(db_path, feed, user_agent, **kwargs):
        captured["db_path"] = db_path
        captured["user_agent"] = user_agent
        captured["kwargs"] = kwargs
        return {"status": "ok", "added": 1, "error": ""}

    monkeypatch.setattr(scheduler.fetcher, "fetch_feed", fake_fetch)

    scheduler._run_tick(
        tmp_db,
        3600,
        "my-agent/1.0",
        12,
        4,
        25,
    )

    assert captured["db_path"] == tmp_db
    assert captured["user_agent"] == "my-agent/1.0"
    assert captured["kwargs"]["timeout"] == 12
    assert captured["kwargs"]["retries"] == 4
    assert captured["kwargs"]["extract_timeout"] == 25


def test_run_tick_skips_not_due(tmp_db, monkeypatch):
    _insert_feed(
        tmp_db,
        interval_min=60,
        last_fetched_at=datetime.now(UTC).isoformat(),
    )

    called: list = []

    def fake_fetch(*args, **kwargs):
        called.append(1)
        return {"status": "ok", "added": 0, "error": ""}

    monkeypatch.setattr(scheduler.fetcher, "fetch_feed", fake_fetch)

    scheduler._run_tick(tmp_db, 3600, "ua", 10, 3, 20)

    assert called == []


def test_run_tick_fetch_exception_continues(tmp_db, monkeypatch):
    _insert_feed(
        tmp_db,
        title="first",
        feed_url="https://example.com/a.xml",
        last_fetched_at=_old_iso(7200),
    )
    _insert_feed(
        tmp_db,
        title="second",
        feed_url="https://example.com/b.xml",
        last_fetched_at=_old_iso(7200),
    )

    seen: list[str] = []

    def fake_fetch(db_path, feed, user_agent, **kwargs):
        seen.append(feed.get("feed_url"))
        if len(seen) == 1:
            raise RuntimeError("boom on first")
        return {"status": "ok", "added": 1, "error": ""}

    monkeypatch.setattr(scheduler.fetcher, "fetch_feed", fake_fetch)

    scheduler._run_tick(tmp_db, 3600, "ua", 10, 3, 20)

    assert len(seen) == 2
    assert scheduler._job_state_get(tmp_db, "last_success_at") != ""


def test_run_tick_error_result_counts_failed(tmp_db, monkeypatch):
    _insert_feed(tmp_db, last_fetched_at=_old_iso(7200))

    def fake_fetch(db_path, feed, user_agent, **kwargs):
        return {"status": "error", "added": 0, "error": "boom"}

    monkeypatch.setattr(scheduler.fetcher, "fetch_feed", fake_fetch)

    scheduler._run_tick(tmp_db, 3600, "ua", 10, 3, 20)

    assert scheduler._job_state_get(tmp_db, "last_success_at") != ""


def test_run_tick_catchup_flag_accepted(tmp_db, monkeypatch):
    _insert_feed(tmp_db, last_fetched_at=_old_iso(7200))

    called: list = []

    def fake_fetch(db_path, feed, user_agent, **kwargs):
        called.append(1)
        return {"status": "ok", "added": 1, "error": ""}

    monkeypatch.setattr(scheduler.fetcher, "fetch_feed", fake_fetch)

    scheduler._run_tick(tmp_db, 3600, "ua", 10, 3, 20, catchup=True)

    assert len(called) == 1
    assert scheduler._job_state_get(tmp_db, "last_tick_at") != ""


def test_start_scheduler_registers_job(app, monkeypatch):
    monkeypatch.setattr(scheduler, "_run_tick", lambda *a, **k: None)

    sched = scheduler.start_scheduler(app)
    try:
        assert sched is scheduler._scheduler
        assert sched.get_job("fetch_tick") is not None
    finally:
        scheduler.shutdown_scheduler()

    scheduler.shutdown_scheduler()


def test_start_scheduler_no_catchup_when_recent(app, monkeypatch, tmp_db):
    db_path = app.config["FEEDFLOW"]["db_path"]
    assert db_path == tmp_db

    scheduler._job_state_set(db_path, "last_tick_at", scheduler._utcnow_iso())

    calls: list = []

    def fake_run_tick(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(scheduler, "_run_tick", fake_run_tick)

    scheduler.start_scheduler(app)
    try:
        assert calls == []
    finally:
        scheduler.shutdown_scheduler()

    scheduler.shutdown_scheduler()


def test_run_tick_no_due_feeds_still_writes_state(tmp_db, monkeypatch):
    called: list = []

    def fake_fetch(*args, **kwargs):
        called.append(1)
        return {"status": "ok", "added": 0, "error": ""}

    monkeypatch.setattr(scheduler.fetcher, "fetch_feed", fake_fetch)

    scheduler._run_tick(tmp_db, 3600, "ua", 10, 3, 20)

    assert called == []
    assert scheduler._job_state_get(tmp_db, "last_tick_at") != ""
    assert scheduler._job_state_get(tmp_db, "last_success_at") != ""
