"""Actual source readers + OS watch + Core routes; no model or native host calls.

These bounded format fixtures test ingestion mechanics, not user-history quality
or an agent's adoption of memory. Do not report them as the four-host acceptance.
"""

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.hy_memory_bridge import HyMemoryBridgeError
from one_memory.imports.sources.registry import build_source_catalog
from one_memory.model_profiles import ModelCapabilities, ModelProfileInput, ProviderKind
from one_memory.secrets import InMemorySecretStore
from tests.source_consent import connection_request


def write_turn(path: Path, source: str, identity: str, role: str, text: str) -> None:
    timestamp = datetime.now(UTC).isoformat()
    if source == "cursor" and path.suffix == ".vscdb":
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)")
            db.execute(
                "INSERT OR IGNORE INTO ItemTable VALUES (?,?)",
                (
                    "composer.composerHeaders",
                    json.dumps({"allComposers": [{"composerId": "native", "isSubagent": False}]}),
                ),
            )
            db.execute(
                "INSERT INTO cursorDiskKV VALUES (?,?)",
                (
                    f"bubbleId:native:{identity}",
                    json.dumps(
                        {"type": 1 if role == "user" else 2, "text": text, "createdAt": timestamp}
                    ),
                ),
            )
        return
    if source == "workbuddy":
        record = {
            "type": "message",
            "sessionId": "native",
            "id": identity,
            "timestamp": timestamp,
            "role": role,
            "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
            "providerData": {"agent": "cli"},
        }
    elif source == "claude-code":
        record = {
            "type": role,
            "sessionId": "native",
            "uuid": identity,
            "timestamp": timestamp,
            "message": {"content": text},
        }
    elif source == "codex":
        record = {
            "type": "response_item",
            "timestamp": timestamp,
            "payload": {
                "type": "message",
                "id": identity,
                "role": role,
                "content": [
                    {"type": "input_text" if role == "user" else "output_text", "text": text}
                ],
            },
        }
    else:
        record = {"role": role, "message": {"content": [{"type": "text", "text": text}]}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


async def eventually(predicate, *, timeout: float = 5) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.025)


@pytest.mark.parametrize(
    "source,storage",
    [
        ("workbuddy", "jsonl"),
        ("claude-code", "jsonl"),
        ("codex", "jsonl"),
        ("cursor", "jsonl"),
        ("cursor", "sqlite"),
    ],
)
def test_each_primary_source_imports_the_last_burst_and_stops_on_revocation(
    tmp_path, source, storage, monkeypatch
):
    monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)

    async def scenario():
        home = tmp_path / "home"
        roots = {
            "workbuddy": home / ".workbuddy/projects",
            "claude-code": home / ".claude/projects",
            "codex": home / ".codex/sessions",
            "cursor": home
            / ("Library/Application Support/Cursor/User" if storage == "sqlite" else ".cursor"),
        }
        root = roots[source]
        root.mkdir(parents=True)
        filename = (
            root / "globalStorage/state.vscdb"
            if storage == "sqlite"
            else (
                root / "projects/project/agent-transcripts/native/native.jsonl"
                if source == "cursor"
                else root / "rollout-native.jsonl"
            )
        )
        baseline_text = "已有原话：预算<5，不能变成预算>5。"
        fresh_text = "新增用户原话：只允许这个来源。"
        last_text = "新增助手报告：建议周三复核，尚未验收。"
        write_turn(filename, source, "initial", "user", baseline_text)
        settings = Settings(
            data_dir=tmp_path / "data",
            source_home=home,
            api_token=SecretStr("isolated-test"),
            automatic_memory_processing=False,
            live_sync_interval_seconds=3600,
            live_sync_watch_debounce_seconds=0.05,
            live_sync_watch_min_interval_seconds=1,
        )
        app = create_app(
            settings,
            source_catalog=build_source_catalog(
                home=home,
                environment={},
                platform="darwin" if source == "cursor" and storage == "sqlite" else None,
            ),
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer isolated-test"},
            ) as client,
        ):
            assert (await client.get("/api/v1/onboarding")).json()["status"] == "not_started"
            assert app.state.evidence_store.count() == 0
            connected = await client.post(
                "/api/v1/sources/connect",
                json=await connection_request(
                    client,
                    [source],
                    onboarding=True,
                    full_rescan=True,
                    enable_sync=True,
                ),
            )
            assert connected.status_code == 200
            assert connected.json()["accepted_source_ids"] == [source]
            await eventually(lambda: app.state.evidence_store.count() == 1)
            assert (await client.post("/api/v1/onboarding/complete")).status_code == 200
            watch = app.state.live_sync_watch
            assert watch is not None and watch.watching == (source,)
            await asyncio.sleep(0.2)
            write_turn(filename, source, "fresh", "user", fresh_text)
            await eventually(lambda: app.state.evidence_store.count() == 2)
            await eventually(lambda: not watch._workers)
            drain = watch._drain_source
            entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
            dispatched = []

            async def held_drain(source_id):
                assert source_id == source
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
                dispatched.append(source_id)
                await drain(source_id)

            # Keep the real OS watcher/queue/readers; only hold this instance's
            # drain before it consumes pending work. No one-second timing race.
            with monkeypatch.context() as patch:
                patch.setattr(watch, "_drain_source", held_drain)
                try:
                    # Positive control: the final write lands after releasing
                    # the same gate used below, with no further filesystem write.
                    write_turn(filename, source, "last", "assistant", last_text)
                    await asyncio.wait_for(entered.wait(), 5)
                    assert source in watch._pending
                    assert app.state.evidence_store.count() == 2
                    release.set()
                    await eventually(lambda: app.state.evidence_store.count() == 3)
                    await eventually(lambda: not watch._workers)
                    assert dispatched == [source] and not cancelled.is_set()
                    receipt = await client.get(f"/api/v1/sources/{source}/import-receipt")
                    assert receipt.status_code == 200
                    assert receipt.json()["messages"] == 3
                    assert receipt.json()["person_messages"] == 2
                    assert receipt.json()["agent_messages"] == 1
                    excerpts = {item["excerpt"] for item in receipt.json()["examples"]}
                    assert excerpts == {baseline_text, fresh_text, last_text}
                    assert (await client.get("/api/v1/memories")).json() == []
                    assert (await client.get("/api/v1/memory-tasks")).json() == []
                    # Same physical file replay is not a second copy of its
                    # messages — and with the file already read to its end there
                    # is no work to open a job for, so the poll declines to.
                    before = len(app.state.import_job_store.list_jobs())
                    job = await app.state.live_sync_supervisor.trigger(source)
                    assert job is None
                    assert len(app.state.import_job_store.list_jobs()) == before
                    assert app.state.evidence_store.count() == 3
                    entered.clear()
                    release.clear()
                    write_turn(filename, source, "pending", "user", "节流期间尚未读取的原话")
                    await asyncio.wait_for(entered.wait(), 5)
                    assert source in watch._pending
                    assert app.state.evidence_store.count() == 3
                    assert not watch._workers[source].done()
                    assert (
                        await client.post(f"/api/v1/sources/{source}/revoke")
                    ).status_code == 200
                    assert cancelled.is_set()
                    assert watch._task is None and watch._workers == {} and watch._pending == {}
                    release.set()
                    assert dispatched == [source], "revoked pending work reached the real drain"
                finally:
                    release.set()
            write_turn(filename, source, "denied", "user", "撤权后的原话不可导入")
            await asyncio.sleep(1.1)
            assert app.state.evidence_store.count() == 3
            assert (await client.get(f"/api/v1/sources/{source}/import-receipt")).status_code == 403

    asyncio.run(scenario())


@pytest.mark.parametrize("source", ["workbuddy", "claude-code", "codex", "cursor"])
def test_automatic_native_ingest_reaches_hy_and_a_failed_hy_never_fabricates_memory(
    tmp_path, source, monkeypatch
):
    monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)

    async def scenario():
        home = tmp_path / "home"
        relative = {
            "workbuddy": ".workbuddy/projects",
            "claude-code": ".claude/projects",
            "codex": ".codex/sessions",
            "cursor": ".cursor",
        }
        root = home / relative[source]
        root.mkdir(parents=True)
        filename = (
            root / "projects/project/agent-transcripts/native/native.jsonl"
            if source == "cursor"
            else root / "rollout-native.jsonl"
        )
        user_text = "新会话用户原话：预算<5。"
        agent_text = "助手只提出建议，尚未获得确认。"
        next_text = "用户补充：先做本地验证。"
        next_agent_text = "助手确认：先做本地验证。"
        write_turn(filename, source, "user", "user", user_text)
        write_turn(filename, source, "assistant", "assistant", agent_text)
        requests = []

        class FailingHy:
            async def ingest(self, request):
                requests.append(request)
                raise HyMemoryBridgeError("hy_memory_unavailable")

            async def close(self):
                pass

        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("isolated-test"),
                live_sync_interval_seconds=3600,
                live_sync_watch_debounce_seconds=0.05,
                live_sync_watch_min_interval_seconds=1,
            ),
            source_catalog=build_source_catalog(home=home, environment={}),
            secret_store=InMemorySecretStore(),
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer isolated-test"},
            ) as client,
        ):
            bridge = FailingHy()

            @asynccontextmanager
            async def isolated_context(lease, _secret, _directory):
                lease.recheck()
                yield bridge

            app.state.memory_processing_supervisor.permission_bridge_factory = isolated_context
            profiles, secrets = app.state.model_profile_store, app.state.secret_store
            profile = profiles.create(
                ModelProfileInput(
                    name="Failure injection, no network model",
                    provider_kind=ProviderKind.OLLAMA,
                    base_url="http://127.0.0.1:1",
                    model="fixture",
                ),
                secrets,
            )
            profiles.record_capabilities(
                profile.profile_id,
                expected_revision=profile.revision,
                capabilities=ModelCapabilities(
                    endpoint_reachable=True,
                    model_available=True,
                    structured_output=True,
                    embedding_available=True,
                ),
                secrets=secrets,
            )
            profiles.activate(profile.profile_id, secrets)
            connected = await client.post(
                "/api/v1/sources/connect",
                json=await connection_request(client, [source], enable_sync=True),
            )
            assert connected.status_code == 200
            for job in connected.json()["jobs"]:
                await app.state.import_supervisor.wait(job["job_id"])
            assert requests == []
            records = app.state.evidence_store.list_conversation(
                app.state.evidence_store.list_conversation_seeds()[0].evidence_id
            )
            permissions = app.state.model_content_permissions
            snapshot = permissions.snapshot(
                user_id="local",
                source_ids=(source,),
                profile=profiles.snapshot(profile.profile_id, profile.revision),
                evidence=records,
                include_future_additions=True,
            )
            permissions.grant(snapshot, user_confirmed=True, expected_revision=0)
            await app.state.memory_processing_supervisor.backfill_off_thread()
            await eventually(lambda: bool(requests))
            first = requests[0]
            assert [turn.content for turn in first.turns] == [user_text, agent_text]
            assert [turn.role for turn in first.turns] == ["user", "assistant"]
            assert {record.source_id for record in first.source_context.current} == {source}
            await asyncio.sleep(0.2)
            write_turn(filename, source, "next", "user", next_text)
            await eventually(lambda: app.state.evidence_store.count() == 3)
            write_turn(filename, source, "next-assistant", "assistant", next_agent_text)
            await eventually(
                lambda: any(next_text in [t.content for t in request.turns] for request in requests)
            )
            await eventually(
                lambda: any(
                    task.status == "waiting_for_model"
                    and task.last_error_code == "hy_memory_unavailable"
                    for task in app.state.memory_task_store.list()
                )
            )
            assert app.state.evidence_store.count() == 4
            assert (await client.get("/api/v1/memories")).json() == []
            assert all(task.status != "completed" for task in app.state.memory_task_store.list())

    asyncio.run(scenario())
