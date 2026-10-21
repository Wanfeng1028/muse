import asyncio
import json
import threading
import time
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from one_memory.call_event_store import CallEventStore
from one_memory.database_access import main_database
from tests.test_context_api import AUTH, headers, post
from tests.test_context_api import app as app
from tests.test_context_api import database as database


@pytest.fixture
def recorded_app(app, database):
    store = CallEventStore(database, retention_days=30, max_events=100)
    store.initialize()
    app.state.call_event_store = store
    app.state.call_event_recording_error = False
    app.state.settings.call_event_retention_days = 30
    app.state.settings.call_event_max_events = 100
    return app


def test_query_records_only_final_metadata_and_trusted_host(recorded_app):
    auth = headers(["om_recall", "om_conversations"]) | {"x-one-memory-host-id": "codex"}
    response = post(recorded_app, auth=auth)
    assert response.status_code == 200
    assert response.headers["x-one-memory-call-recorded"] == "true"
    events = recorded_app.state.call_event_store.list()
    assert events.total == 1
    event = events.items[0]
    assert str(event.event_id) == response.json()["request_id"]
    assert event.host_id == "codex" and event.raw_count > 0 and event.memory_count > 0
    assert event.delivery == "unknown" and event.adoption == "unknown"
    assert event.stage == "core_result"
    assert event.host_session_id is None and event.injection_elapsed_ms is None
    encoded = event.model_dump_json()
    assert "needle" not in encoded and "governed summary" not in encoded
    assert "original statement" not in encoded
    assert {ref.kind for ref in event.references} == {"raw", "memory"}


def test_delivery_report_is_separate_from_adoption(recorded_app):
    response = post(recorded_app)
    event_id = response.json()["request_id"]

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=recorded_app), base_url="http://test"
        ) as client:
            delivered = await client.post(
                f"/api/v1/call-events/{event_id}/delivery",
                headers=AUTH,
                json={
                    "delivery": "delivered",
                    "host_session_id": "workbuddy-session-1",
                    "injection_elapsed_ms": 804.25,
                },
            )
            assert delivered.status_code == 200
            assert delivered.json() == {
                "delivery": "delivered",
                "adoption": "unknown",
            }

            late = await client.post(
                f"/api/v1/call-events/{event_id}/delivery",
                headers=AUTH,
                json={
                    "delivery": "not_delivered",
                    "host_session_id": "workbuddy-session-2",
                    "injection_elapsed_ms": 1,
                },
            )
            assert late.status_code == 200
            assert late.json() == {
                "delivery": "delivered",
                "adoption": "unknown",
            }

    asyncio.run(scenario())
    event = recorded_app.state.call_event_store.get(UUID(event_id))
    assert event.delivery == "delivered"
    assert event.adoption == "unknown"
    assert event.host_session_id == "workbuddy-session-1"


def test_delivery_report_rejects_hosts_and_missing_events(recorded_app):
    event_id = post(recorded_app).json()["request_id"]
    payload = {
        "delivery": "delivered",
        "host_session_id": "workbuddy-session-1",
        "injection_elapsed_ms": 10,
    }

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=recorded_app), base_url="http://test"
        ) as client:
            denied = await client.post(
                f"/api/v1/call-events/{event_id}/delivery",
                headers=headers(["om_ask"]),
                json=payload,
            )
            assert denied.status_code == 403
            missing = await client.post(
                f"/api/v1/call-events/{uuid4()}/delivery",
                headers=AUTH,
                json=payload,
            )
            assert missing.status_code == 404
            assert missing.json()["detail"] == "call_event_not_found"

    asyncio.run(scenario())


def test_delivery_report_rejects_non_metadata_session_values(recorded_app):
    event_id = post(recorded_app).json()["request_id"]

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=recorded_app), base_url="http://test"
        ) as client:
            for session_id in ("private\ntext", "/private/session.jsonl", "x" * 129):
                response = await client.post(
                    f"/api/v1/call-events/{event_id}/delivery",
                    headers=AUTH,
                    json={
                        "delivery": "delivered",
                        "host_session_id": session_id,
                        "injection_elapsed_ms": 10,
                    },
                )
                assert response.status_code == 422

    asyncio.run(scenario())


def test_explicit_feedback_records_a_local_label_without_claiming_adoption(recorded_app):
    response = post(recorded_app)
    event_id = response.json()["request_id"]
    payload = {
        "search_event_id": event_id,
        "feedback_kind": "relevant",
        "selected_refs": [
            {
                "kind": "raw",
                "reference_id": response.json()["items"][0]["messages"][0]["evidence_id"],
                "revision": response.json()["items"][0]["messages"][0]["revision"],
            }
        ],
        "actor": "user",
        "signal": "explicit_feedback",
        "consent_version": 1,
        "retention_days": 30,
    }

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=recorded_app), base_url="http://test"
        ) as client:
            accepted = await client.post(
                "/api/v1/call-events/feedback",
                headers=AUTH,
                json=payload,
            )
            assert accepted.status_code == 200
            assert accepted.json() == {"stage": "feedback", "adoption": "unknown"}
            assert (
                await client.post(
                    "/api/v1/call-events/feedback",
                    headers=headers(["om_recall"]),
                    json=payload,
                )
            ).status_code == 403
            not_returned = {
                **payload,
                "selected_refs": [{**payload["selected_refs"][0], "revision": 99}],
            }
            invalid = await client.post(
                "/api/v1/call-events/feedback",
                headers=AUTH,
                json=not_returned,
            )
            assert invalid.status_code == 422
            assert invalid.json()["detail"] == "call_event_feedback_invalid"
            events = recorded_app.state.call_event_store.list()
            assert events.total == 2
            label = events.items[0]
            assert label.stage == "feedback" and label.adoption == "unknown"
            assert label.feedback is not None
            assert (
                label.feedback.selected_refs[0].revision
                == response.json()["items"][0]["messages"][0]["revision"]
            )

    asyncio.run(scenario())


def test_probes_never_create_events_but_real_empty_query_does(recorded_app):
    for _ in range(10):
        assert post(recorded_app, {"query": "__om_probe__"}).status_code == 200
    assert recorded_app.state.call_event_store.list().total == 0
    response = post(recorded_app, {"query": "no-match-private-query"})
    assert response.status_code == 200
    event = recorded_app.state.call_event_store.list().items[0]
    assert event.state == "empty" and not event.references
    assert "no-match-private-query" not in event.model_dump_json()


def test_recording_failure_preserves_query_and_reports_unrecorded(recorded_app, monkeypatch):
    def fail(_event):
        raise OSError("PRIVATE_FAILURE")

    monkeypatch.setattr(recorded_app.state.call_event_store, "record", fail)
    response = post(recorded_app)
    assert response.status_code == 200 and response.json()["items"]
    assert response.headers["x-one-memory-call-recorded"] == "false"
    assert "PRIVATE_FAILURE" not in response.text
    assert recorded_app.state.call_event_recording_error is True


def test_a_held_writer_does_not_hold_the_context_response(recorded_app, database):
    """Call-event metadata must not turn a held writer into a 5s response.

    C0 measured p95 2037.9ms with an 8s writer hold because
    `CallEventStore.record -> database.write()` consumed the default 5s
    budget. The route now bounds only this metadata write and returns the
    completed context response with `X-One-Memory-Call-Recorded: false`.
    """
    release = threading.Event()
    held = threading.Event()

    def hold_writer() -> None:
        with main_database(database).write() as writer, writer:
            writer.execute("BEGIN IMMEDIATE")
            held.set()
            release.wait(10)

    holder = threading.Thread(target=hold_writer, daemon=True)
    holder.start()
    assert held.wait(5)
    started = time.monotonic()
    try:
        response = post(recorded_app)
    finally:
        release.set()
        holder.join(timeout=10)
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.json()["items"]
    assert elapsed < 1.0, f"held-writer response waited {elapsed:.3f}s"
    assert response.headers["x-one-memory-call-recorded"] == "false"
    assert recorded_app.state.call_event_recording_error is True


def test_twenty_held_writer_requests_keep_the_response_bounded(recorded_app, database):
    """The F1 probe shape, exercised on the real route fixture."""
    release = threading.Event()
    held = threading.Event()

    def hold_writer() -> None:
        with main_database(database).write() as writer, writer:
            writer.execute("BEGIN IMMEDIATE")
            held.set()
            release.wait(12)

    holder = threading.Thread(target=hold_writer, daemon=True)
    holder.start()
    assert held.wait(5)
    samples: list[float] = []
    recorded: list[str] = []
    response_elapsed_ms: list[float] = []
    try:
        for _ in range(20):
            started = time.monotonic()
            response = post(recorded_app)
            elapsed_ms = (time.monotonic() - started) * 1000
            response_elapsed_ms.append(elapsed_ms)
            samples.append(elapsed_ms)
            recorded.append(response.headers["x-one-memory-call-recorded"])
            assert response.status_code == 200 and response.json()["items"]
    finally:
        release.set()
        holder.join(timeout=12)
    p95 = sorted(samples)[18]
    assert sum(value <= 1500 for value in samples) == 20, sorted(samples)
    assert sum(value <= 3500 for value in samples) == 20, sorted(samples)
    assert recorded == ["false"] * 20
    raw = {
        "measurement_point": "immediately_after_http_post_returns",
        "waits_for_background_record": False,
        "response_elapsed_ms": response_elapsed_ms,
        "headers": recorded,
        "p50_ms": sorted(samples)[9],
        "p95_ms": p95,
        "max_ms": max(samples),
        "under_1500ms": sum(value <= 1500 for value in samples),
        "under_3500ms": sum(value <= 3500 for value in samples),
    }
    print("\n" + json.dumps(raw, sort_keys=True))


def test_history_local_only_and_exact_clear_preserves_memory(recorded_app):
    response = post(recorded_app)
    event_id = response.json()["request_id"]
    UUID(event_id)

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=recorded_app), base_url="http://test"
        ) as client:
            history = await client.get("/api/v1/call-events", headers=AUTH)
            assert history.status_code == 200 and history.json()["total"] == 1
            assert history.headers["cache-control"] == "no-store"
            assert history.json()["available"] is True
            resolved = await client.get(f"/api/v1/call-events/{event_id}/references", headers=AUTH)
            assert resolved.status_code == 200 and resolved.json()
            assert all(item["available"] for item in resolved.json())
            assert resolved.headers["cache-control"] == "no-store"
            assert (
                await client.get(
                    f"/api/v1/call-events/{event_id}/references", headers=headers(["om_recall"])
                )
            ).status_code == 403
            assert (await client.get("/api/v1/call-events")).status_code == 401
            assert (
                await client.get("/api/v1/call-events", headers=headers(["om_recall"]))
            ).status_code == 403
            assert (
                await client.post(
                    "/api/v1/call-events/clear",
                    headers=AUTH,
                    json={"event_ids": [event_id], "user_confirmed": False},
                )
            ).status_code == 422
            cleared = await client.post(
                "/api/v1/call-events/clear",
                headers=AUTH,
                json={"event_ids": [event_id], "user_confirmed": True},
            )
            assert cleared.json() == {"removed": 1}
            assert (
                await client.get(f"/api/v1/call-events/{event_id}/references", headers=AUTH)
            ).status_code == 404
            assert (await client.get("/api/v1/call-events", headers=AUTH)).json()["total"] == 0

    asyncio.run(scenario())
    assert post(recorded_app).json()["items"]


def test_default_settings_enable_bounded_call_history():
    from one_memory.config import Settings

    settings = Settings(_env_file=None)
    assert settings.call_event_retention_days == 30
    assert settings.call_event_max_events == 10_000


def test_disabled_policy_does_not_claim_empty_history(app):
    app.state.settings.call_event_retention_days = None
    app.state.settings.call_event_max_events = None
    app.state.call_event_store = None

    async def scenario():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            result = await client.get("/api/v1/call-events", headers=AUTH)
            assert result.status_code == 200
            assert result.json()["available"] is False

    asyncio.run(scenario())


def test_confirmed_clear_all_preserves_memory_and_rejects_hosts(recorded_app):
    first = post(recorded_app).json()["request_id"]
    second = post(recorded_app).json()["request_id"]
    UUID(first)
    UUID(second)

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=recorded_app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/v1/call-events", headers=AUTH)).json()["total"] == 2
            assert (
                await client.post(
                    "/api/v1/call-events/clear-all",
                    headers=AUTH,
                    json={"user_confirmed": False},
                )
            ).status_code == 422
            assert (
                await client.post(
                    "/api/v1/call-events/clear-all",
                    headers=headers(["om_recall"]),
                    json={"user_confirmed": True},
                )
            ).status_code == 403
            cleared = await client.post(
                "/api/v1/call-events/clear-all",
                headers=AUTH,
                json={"user_confirmed": True},
            )
            assert cleared.json() == {"removed": 2}
            assert (await client.get("/api/v1/call-events", headers=AUTH)).json()["total"] == 0
            assert (
                await client.post(
                    "/api/v1/call-events/clear-all",
                    headers=AUTH,
                    json={"user_confirmed": True},
                )
            ).json() == {"removed": 0}

    asyncio.run(scenario())
    assert post(recorded_app).json()["items"]


def test_legacy_probe_exclusion_and_empty_call_metadata(recorded_app):
    from types import SimpleNamespace

    from one_memory.recall import RecallReceipt, RecallRequest, RecallState, _probe_receipt

    class Target:
        filter_memories = staticmethod(tuple)

        async def recall_async(self, request):
            if request.query == "__om_probe__":
                return _probe_receipt(request)
            return RecallReceipt(
                state=RecallState.EMPTY,
                query=request.query,
                scope=request.scope,
                hits=(),
                used_characters=0,
                truncated=False,
            )

    recorded_app.state.recall_target = Target()
    recorded_app.state.source_read_access = SimpleNamespace()

    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=recorded_app), base_url="http://test", headers=AUTH
        ) as client:
            for _ in range(3):
                response = await client.post(
                    "/api/v1/recall", json=RecallRequest(query="__om_probe__").model_dump()
                )
                assert response.status_code == 200
            assert recorded_app.state.call_event_store.list().total == 0
            response = await client.post("/api/v1/recall", json={"query": "private legacy query"})
            assert response.status_code == 200
            events = recorded_app.state.call_event_store.list()
            assert events.total == 1 and events.items[0].state == "empty"
            assert "private legacy query" not in events.model_dump_json()

    asyncio.run(scenario())


def test_conversation_only_context_is_not_labeled_recall(recorded_app):
    auth = headers(["om_conversations"]) | {"x-one-memory-host-id": "codex"}
    response = post(recorded_app, auth=auth)
    assert response.status_code == 200
    event = recorded_app.state.call_event_store.list().items[0]
    assert event.tool == "om_conversations"
    assert event.raw_count > 0 and event.memory_count == 0


def test_recording_error_stays_after_later_success(recorded_app, monkeypatch):
    store = recorded_app.state.call_event_store
    original = store.record

    def fail(_event):
        raise OSError("PRIVATE_FAILURE")

    monkeypatch.setattr(store, "record", fail)
    failed = post(recorded_app)
    assert failed.status_code == 200
    assert recorded_app.state.call_event_recording_error is True
    monkeypatch.setattr(store, "record", original)
    recovered = post(recorded_app)
    assert recovered.headers["x-one-memory-call-recorded"] == "true"
    assert recorded_app.state.call_event_recording_error is True
    assert store.list().total == 1


def test_partial_retention_settings_are_rejected():
    from pydantic import ValidationError

    from one_memory.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, call_event_retention_days=30, call_event_max_events=None)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, call_event_retention_days=None)


def test_host_tools_record_metadata_without_bodies(tmp_path):
    from pydantic import SecretStr

    from one_memory.api import create_app
    from one_memory.config import Settings
    from one_memory.imports.models import (
        EvidenceInput,
        EvidenceOrigin,
        OriginMetadata,
        WrittenBy,
    )
    from one_memory.memory_qa import MemoryAnswer

    class Answerer:
        filter_memories = staticmethod(tuple)
        resolve_workspace = None

        async def answer(self, question, **kwargs):
            return MemoryAnswer(answer="SECRET_ASK_ANSWER", memories=(), mode="empty")

        async def answer_stream(self, question, **kwargs):
            yield {
                "type": "final",
                "answer": "SECRET_STREAM_ANSWER",
                "memories": (),
                "mode": "empty",
            }

    async def scenario():
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path,
                api_token=SecretStr("local-token"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer local-token",
                    "Origin": "http://127.0.0.1:5173",
                },
            ) as client,
        ):
            app.state.evidence_store.put(
                EvidenceInput(
                    user_id="local",
                    source_id="cursor",
                    conversation_id="conversation-1",
                    message_id="message-1",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    created_at=None,
                    verbatim="抽取终于跑通了",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            )
            app.state.memory_answerer = Answerer()
            local = await client.get(
                "/api/v1/conversations/search", params={"query": "SECRET_QUERY_抽取"}
            )
            assert local.status_code == 200
            assert app.state.call_event_store.list().total == 0
            external = headers(["om_conversations", "om_ask", "om_matters"]) | {
                "Authorization": "Bearer local-token",
                "x-one-memory-host-id": "cursor",
            }
            found = await client.get(
                "/api/v1/conversations/search",
                params={"query": "SECRET_QUERY_抽取"},
                headers=external,
            )
            asked = await client.post(
                "/api/v1/memories/ask",
                json={"question": "SECRET_ASK_QUESTION"},
                headers=external,
            )
            streamed = await client.post(
                "/api/v1/memories/ask/stream",
                json={"question": "SECRET_STREAM_QUESTION"},
            )
            matters = await client.post(
                "/api/v1/matters/context/search",
                json={"query": "SECRET_MATTER_QUERY"},
                headers=external,
            )
            probe = await client.get(
                "/api/v1/conversations/search",
                params={"query": "__om_probe__"},
                headers=external,
            )
            assert found.status_code == 200
            assert asked.status_code == 200
            assert streamed.status_code == 200
            assert matters.status_code == 200
            assert probe.status_code == 200
            assert found.headers["x-one-memory-call-recorded"] == "true"
            assert asked.headers["x-one-memory-call-recorded"] == "true"
            assert matters.headers["x-one-memory-call-recorded"] == "true"
            events = app.state.call_event_store.list()
            tools = {event.tool for event in events.items}
            assert tools == {"om_conversations", "om_ask", "om_matters"}
            assert events.total == 3
            assert sum(event.tool == "om_ask" for event in events.items) == 1
            encoded = events.model_dump_json()
            assert "SECRET" not in encoded
            assert "抽取终于" not in encoded
            assert all(event.host_id == "cursor" for event in events.items)
            assert all(event.installation_id is not None for event in events.items)

    asyncio.run(scenario())
