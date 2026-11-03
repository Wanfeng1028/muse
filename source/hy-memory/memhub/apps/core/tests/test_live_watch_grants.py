import asyncio
import json
import time

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.sources.registry import build_source_catalog
from tests.source_consent import authorized_request, connection_request


@pytest.mark.parametrize("connect", [True, False])
def test_explicit_sync_grant_starts_watch_without_restart_and_revocation_stops_it(
    tmp_path, connect
):
    async def scenario():
        home = tmp_path / "home"
        projects = home / ".claude/projects"
        projects.mkdir(parents=True)
        settings = Settings(
            data_dir=tmp_path / "data",
            source_home=home,
            api_token=SecretStr("test"),
            automatic_memory_processing=False,
            live_sync_interval_seconds=3600,
            live_sync_watch_debounce_seconds=0.1,
            live_sync_watch_min_interval_seconds=1,
        )
        app = create_app(
            settings,
            source_catalog=build_source_catalog(home=home, environment={}, platform="darwin"),
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test"},
            ) as client,
        ):
            assert app.state.live_sync_watch is None
            if connect:
                result = await client.post(
                    "/api/v1/sources/connect",
                    json=await connection_request(client, ["claude-code"]),
                )
            else:
                result = await client.post(
                    "/api/v1/sources/claude-code/authorize",
                    json=await authorized_request(client, "claude-code"),
                )
            assert result.status_code == 200
            assert app.state.live_sync_watch is None
            sync = await client.post(
                "/api/v1/sources/claude-code/sync-permission",
                json={"enabled": True},
            )
            assert sync.status_code == 200
            watcher = app.state.live_sync_watch
            assert watcher is not None and watcher.watching == ("claude-code",)
            # Wait for the initial empty scan and OS watch registration.
            for job in app.state.import_job_store.list_jobs():
                await app.state.import_supervisor.wait(job.job_id)
            await asyncio.sleep(0.3)
            start = time.monotonic()
            transcript = projects / "new.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "s",
                        "uuid": "m",
                        "message": {"content": "visible new turn"},
                    }
                )
                + "\n"
            )
            # A brand-new file is first anchored at EOF by the live path so
            # history owns its old contents. The real-time contract is the
            # append that follows that anchor.
            await app.state.live_sync_supervisor.trigger("claude-code")
            with transcript.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {
                            "type": "assistant",
                            "sessionId": "s",
                            "uuid": "m2",
                            "message": {"content": "visible appended turn"},
                        }
                    )
                    + "\n"
                )
            await app.state.live_sync_supervisor.trigger("claude-code")
            while app.state.evidence_store.count() == 0 and time.monotonic() - start < 5:
                await asyncio.sleep(0.05)
            assert app.state.evidence_store.count() == 1
            health = (await client.get("/api/v1/live-sync")).json()
            assert (
                next(item for item in health if item["source_id"] == "claude-code")["mode"]
                == "watch_and_polling"
            )
            await client.post("/api/v1/sources/claude-code/revoke")
            assert app.state.live_sync_watch is None
            assert watcher._task is None
            # A new unauthorized source file must remain unread.
            (projects / "other.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "s2",
                        "uuid": "m2",
                        "message": {"content": "not authorized"},
                    }
                )
                + "\n"
            )
            await asyncio.sleep(0.3)
            assert app.state.evidence_store.count() == 1

    asyncio.run(scenario())
