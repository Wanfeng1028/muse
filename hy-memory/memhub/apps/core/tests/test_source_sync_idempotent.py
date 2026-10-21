"""Final-state Harness sync is idempotent and resumes missed source work."""

import asyncio
import json

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.sources.registry import build_source_catalog
from one_memory.secrets import InMemorySecretStore
from tests.source_consent import authorized_request


def write_turn(root, identifier):
    (root / f"{identifier}.jsonl").write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": identifier,
                "uuid": identifier,
                "message": {"content": identifier},
            }
        )
        + "\n"
    )


def test_repeating_the_current_state_has_no_duplicate_runtime_work(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)
        home = tmp_path / "home"
        (home / ".claude/projects").mkdir(parents=True)
        app = create_app(
            Settings(
                _env_file=None,
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("test"),
                imports_enabled=True,
                automatic_memory_processing=False,
                live_sync_watch_enabled=False,
                live_sync_interval_seconds=3600,
            ),
            source_catalog=build_source_catalog(home=home, environment={}),
            secret_store=InMemorySecretStore(),
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test"},
            ) as client,
        ):
            authorized = await client.post(
                "/api/v1/sources/claude-code/authorize",
                json=await authorized_request(client, "claude-code"),
            )
            assert authorized.status_code == 200
            first = await client.post(
                "/api/v1/sources/claude-code/sync-permission",
                json={"enabled": True},
            )
            assert first.json() == {
                "source_id": "claude-code",
                "sync_enabled": True,
            }
            before = [job.job_id for job in app.state.import_job_store.list_jobs()]
            repeated = await client.post(
                "/api/v1/sources/claude-code/sync-permission",
                json={"enabled": True},
            )
            assert repeated.json() == first.json()
            assert [job.job_id for job in app.state.import_job_store.list_jobs()] == before

    asyncio.run(scenario())


def test_resume_backfills_content_that_arrived_while_paused(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)
        home = tmp_path / "home"
        root = home / ".claude/projects"
        root.mkdir(parents=True)
        write_turn(root, "before-pause")
        app = create_app(
            Settings(
                _env_file=None,
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("test"),
                imports_enabled=True,
                automatic_memory_processing=False,
                live_sync_watch_enabled=False,
                live_sync_interval_seconds=3600,
            ),
            source_catalog=build_source_catalog(home=home, environment={}),
            secret_store=InMemorySecretStore(),
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test"},
            ) as client,
        ):
            await client.post(
                "/api/v1/sources/claude-code/authorize",
                json=await authorized_request(client, "claude-code"),
            )
            await client.post(
                "/api/v1/sources/claude-code/sync-permission",
                json={"enabled": True},
            )
            for job in app.state.import_job_store.list_jobs():
                await asyncio.wait_for(app.state.import_supervisor.wait(job.job_id), 10)
            assert app.state.evidence_store.count() == 1

            paused = await client.post(
                "/api/v1/sources/claude-code/sync-permission",
                json={"enabled": False},
            )
            assert paused.json()["sync_enabled"] is False
            write_turn(root, "while-paused")
            existing = {job.job_id for job in app.state.import_job_store.list_jobs()}

            resumed = await client.post(
                "/api/v1/sources/claude-code/sync-permission",
                json={"enabled": True},
            )
            assert resumed.json()["sync_enabled"] is True
            catch_up = [
                job for job in app.state.import_job_store.list_jobs() if job.job_id not in existing
            ]
            assert catch_up
            for job in catch_up:
                await asyncio.wait_for(app.state.import_supervisor.wait(job.job_id), 10)
            assert app.state.evidence_store.count() == 2

    asyncio.run(scenario())
