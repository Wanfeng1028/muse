"""3925a kernel item 2 (BUG-01): the session count reaches the authorization page.

The frontend has to show "found N sessions" before the user grants access.
Today the source card carries `detected` as a single boolean, so an installed
host with no transcripts yet and one holding 300 of them are the same payload.
"""

from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.access import source_root_identity
from one_memory.imports.sources.registry import build_source_catalog


def _app(tmp_path, home):
    catalog = build_source_catalog(home=home, environment={}, platform="darwin")
    return (
        create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("test-token"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
                live_sync_watch_enabled=False,
            ),
            source_catalog=catalog,
        ),
        catalog,
    )


def _client(app):
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token"},
    )


def _authorize_codex(app, catalog) -> None:
    registration = catalog["codex"]
    store = app.state.source_grant_store
    store.grant(
        user_id="local",
        source_id="codex",
        root=registration.candidate.path,
        candidate_kind=registration.candidate.kind,
        expected_root_id=source_root_identity(registration.candidate.path),
    )
    grant = store.authorized_root(user_id="local", source_id="codex")
    assert grant is not None
    app.state.import_supervisor.register_adapter(registration.create_adapter(grant))


def test_detect_reports_the_session_count_it_found(tmp_path) -> None:
    async def scenario() -> None:
        home = tmp_path / "home"
        sessions = home / ".codex" / "sessions"
        sessions.mkdir(parents=True)
        for index in range(3):
            (sessions / f"rollout-{index}.jsonl").write_text("{}\n", encoding="utf-8")
        (sessions / "not-a-session.txt").write_text("notes", encoding="utf-8")
        app, catalog = _app(tmp_path, home)

        async with app.router.lifespan_context(app), _client(app) as client:
            _authorize_codex(app, catalog)
            detection = await client.post("/api/v1/sources/codex/detect")

            assert detection.status_code == 200
            assert detection.json()["detected"] is True
            assert detection.json()["session_count"] == 3

            sources = await client.get("/api/v1/sources")
            codex = next(item for item in sources.json() if item["source_id"] == "codex")
            assert codex["session_count"] == 3

    asyncio.run(scenario())


def test_detect_reports_zero_sessions_for_an_installed_but_empty_root(tmp_path) -> None:
    """Installed, nothing to import yet: True and 0, not "not found"."""

    async def scenario() -> None:
        home = tmp_path / "home"
        (home / ".codex" / "sessions").mkdir(parents=True)
        app, catalog = _app(tmp_path, home)

        async with app.router.lifespan_context(app), _client(app) as client:
            _authorize_codex(app, catalog)
            detection = await client.post("/api/v1/sources/codex/detect")

            assert detection.json()["detected"] is True
            assert detection.json()["session_count"] == 0

    asyncio.run(scenario())
