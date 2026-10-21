import sqlite3

from one_memory.home_summary import read_home_summary


def database(tmp_path):
    path = tmp_path / "summary.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE governed_memories(memory_id TEXT, user_id TEXT, status TEXT,
                deleted_at TEXT, content TEXT, revision INTEGER, updated_at TEXT);
            CREATE TABLE governed_memory_evidence(memory_id TEXT, evidence_id TEXT, active INTEGER);
            CREATE TABLE governed_memory_versions(memory_id TEXT, revision INTEGER, action TEXT);
            CREATE TABLE evidence(evidence_id TEXT, user_id TEXT, source_id TEXT);
            CREATE TABLE source_grants(user_id TEXT, source_id TEXT, revoked_at TEXT);
        """)
        db.execute("INSERT INTO evidence VALUES ('e1','local','cursor')")
        db.execute("INSERT INTO evidence VALUES ('e2','local','workbuddy')")
    return path


def put(
    path,
    key,
    *,
    status="confirmed",
    user="local",
    content="Memory",
    time="2026-09-19T01:00:00+00:00",
    deleted=None,
):
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO governed_memories VALUES (?,?,?,?,?,?,?)",
            (key, user, status, deleted, content, 2, time),
        )
        db.execute("INSERT INTO governed_memory_evidence VALUES (?, 'e1', 1)", (key,))
        db.execute("INSERT INTO governed_memory_versions VALUES (?, 2, 'correct')", (key,))


def test_summary_counts_beyond_page_limit_and_excludes_ineligible_rows(tmp_path):
    path = database(tmp_path)
    for i in range(503):
        put(path, str(i))
    put(path, "superseded", status="superseded")
    put(path, "deleted", deleted="2026-09-19T00:00:00+00:00")
    put(path, "other", user="other")
    result = read_home_summary(path)
    assert result.memory_count == 503
    assert result.latest is not None
    assert result.latest.source_ids == ("cursor",)
    assert result.latest.revision == 2
    assert result.latest.action == "correct"


def test_summary_revocation_excludes_whole_mixed_memory_not_only_citation(tmp_path):
    path = database(tmp_path)
    put(path, "mixed", time="2026-09-19T03:00:00+00:00")
    put(path, "retained")
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO governed_memory_evidence VALUES ('mixed','e2',1)")
        db.execute("INSERT INTO source_grants VALUES ('local','workbuddy','revoked')")
    result = read_home_summary(path)
    assert result.memory_count == 1
    assert result.latest.memory_id == "retained"
    with sqlite3.connect(path) as db:
        db.execute("UPDATE governed_memory_evidence SET active=0 WHERE evidence_id='e2'")
    assert read_home_summary(path).memory_count == 2


def test_latest_is_bounded_and_other_users_revocations_do_not_hide_local_data(tmp_path):
    path = database(tmp_path)
    put(path, "first")
    put(path, "latest", time="2026-09-19T02:00:00+00:00", content="x" * 2000)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO source_grants VALUES ('other','cursor','revoked')")
    result = read_home_summary(path)
    assert result.memory_count == 2
    assert result.latest.memory_id == "latest"
    assert result.latest.truncated is True
    assert len(result.latest.content) == 320


def test_empty_summary_is_distinct_from_failed_read(tmp_path):
    path = database(tmp_path)
    result = read_home_summary(path)
    assert result.memory_count == 0
    assert result.latest is None


def test_a_read_past_its_deadline_returns_stale_projection(tmp_path):
    """A timed-out homepage read must not escape as SQLITE_INTERRUPT.

    Real trigger: `/api/v1/home-summary` returned a bare OperationalError,
    sqlite_errorcode 9, because the progress handler installed to bound the
    read is itself what interrupts it and nothing caught the result.
    2026-10-12: instead of raising HomeSummaryUnavailable (which still 500ed
    on builds before fab1f6b6), the read answers a `stale` projection so the
    UI keeps its last good summary on screen.
    """
    import time as time_module

    import one_memory.home_summary as home_summary

    path = database(tmp_path)
    # Enough rows that the progress handler actually gets to tick.
    for index in range(20000):
        put(path, str(index))
    # Expire the deadline up front: the progress handler installed to bound
    # the read then interrupts on its first tick, which is exactly the
    # slow-machine path.
    real = time_module.monotonic
    home_summary.time = type("ExpiredClock", (), {"monotonic": staticmethod(lambda: real() + 100)})
    try:
        result = read_home_summary(path)
    except Exception as error:  # noqa: BLE001 - nothing may escape
        raise AssertionError(
            f"a bare {type(error).__name__} "
            f"(sqlite_errorcode={getattr(error, 'sqlite_errorcode', '-')}) escaped"
        ) from error
    finally:
        home_summary.time = time_module
    assert result.stale is True
    assert result.memory_count == 0
    assert result.latest is None


def test_home_summary_api_is_authenticated_and_has_typed_empty_state(tmp_path):
    import asyncio

    from httpx import ASGITransport, AsyncClient
    from pydantic import SecretStr

    from one_memory.api import create_app
    from one_memory.config import Settings

    async def scenario():
        home = tmp_path / "home"
        home.mkdir()
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("synthetic-token"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            ),
            source_catalog={},
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            denied = await client.get("/api/v1/home-summary")
            assert denied.status_code in (401, 403)
            result = await client.get(
                "/api/v1/home-summary", headers={"Authorization": "Bearer synthetic-token"}
            )
            assert result.status_code == 200
            assert result.json()["memory_count"] == 0
            assert result.json()["latest"] is None
            assert result.json()["observed_at"]

    asyncio.run(scenario())
