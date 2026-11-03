import asyncio
import json
import random
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.imports.grants import GRANT_SCHEMA
from one_memory.imports.jobs import ImportStatus
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.sources.registry import build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.matters.selection import select_evidence
from one_memory.memory_processing import _conversation_chunks
from one_memory.secrets import InMemorySecretStore
from tests.source_consent import authorized_request


@pytest.fixture(autouse=True)
def _segment_at_the_legacy_window(monkeypatch):
    """These cases exercise segmenting a single over-ceiling message (D74).

    The ceiling is now 60,000 characters of what HY reads; pin it to the old
    12,000 so the 12,001-character fixtures still cross it.
    """
    import one_memory.memory_processing as memory_processing

    monkeypatch.setattr(memory_processing, "_WHOLE_TURN_CHARACTERS", 12_000)


@pytest.mark.parametrize("length", [25, 53, 91])
def test_hy_windows_cover_every_turn_including_leading_and_boundary_assistants(tmp_path, length):
    _, records = library(tmp_path, {"session": [f"Turn {i}. " * 20 for i in range(length)]})
    records[0] = records[0].model_copy(update={"role": "assistant", "written_by": WrittenBy.AGENT})
    chunks = _conversation_chunks(records, max_turns=6, max_characters=1200)
    assert {r.evidence_id for c in chunks for r in c} == {r.evidence_id for r in records}
    assert all(len(c) <= 6 and sum(len(r.verbatim) for r in c) <= 1200 for c in chunks)


def test_oversize_turn_is_split_without_silently_dropping_content(tmp_path):
    _, records = library(tmp_path, {"session": ["A short request", "long response " * 1000]})
    chunks = _conversation_chunks(records)

    assert len(chunks) > 1
    assert all(sum(len(record.verbatim) for record in chunk) <= 12_000 for chunk in chunks)
    assert all(chunk[0].verbatim == "A short request" for chunk in chunks)
    segments = [record for chunk in chunks for record in chunk[1:]]
    assert "".join(segment.verbatim for segment in segments) == records[1].verbatim
    assert all(
        any(
            "one_memory_segment_v1" in metadata.raw_meta
            for metadata in segment.origin_meta.values()
        )
        for segment in segments
    )


def test_partial_timestamps_preserve_source_sequence(tmp_path):
    path, records = library(
        tmp_path, {"session": ["Initial decision", "Correction", "Acknowledged"]}
    )
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE evidence SET created_at=NULL WHERE evidence_id=?", (records[1].evidence_id,)
        )
    selected = select_evidence(path)
    assert [r.evidence_id for r in selected.records] == [r.evidence_id for r in records]
    assert selected.records[1].created_at is None


def library(tmp_path, conversations):
    path = tmp_path / "library.sqlite3"
    store = EvidenceStore(path)
    with sqlite3.connect(path) as db:
        db.executescript(GRANT_SCHEMA)
        db.execute(
            "INSERT INTO source_grants VALUES ('local','codex','/authorized','default',?,NULL)",
            (datetime.now(UTC).isoformat(),),
        )
    saved = []
    for session, messages in conversations.items():
        for index, text in enumerate(messages):
            saved.append(
                store.put(
                    EvidenceInput(
                        source_id="codex",
                        conversation_id=session,
                        message_id=f"message-{index}",
                        source_ordinal=f"file:byte:{index * 10}",
                        role="user" if index % 2 == 0 else "assistant",
                        written_by=WrittenBy.PERSON if index % 2 == 0 else WrittenBy.AGENT,
                        created_at=datetime(2026, 9, 1, tzinfo=UTC) + timedelta(seconds=index),
                        verbatim=text,
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
            )
    return path, saved


@pytest.mark.parametrize("length", [7, 33, 79])
def test_budget_never_silently_removes_middle_of_a_conversation(tmp_path, length):
    randomizer = random.Random(length)
    texts = [f"Message {i}: " + "x" * randomizer.randint(30, 120) for i in range(length)]
    middle = length // 2
    texts[middle] = "Important changed requirement " * 80
    path, records = library(tmp_path, {"unnamed-session": texts})
    result = select_evidence(path, max_chars=sum(map(len, texts)) - 100)
    ids = {r.evidence_id for r in result.records}
    assert not ids or ids == {r.evidence_id for r in records}
    assert not result.coverage_complete
    assert result.deferred_conversations[0].records == length
    assert result.deferred_conversations[0].reason == "character_budget"


def test_first_pass_keeps_all_sessions_and_short_user_requirements(tmp_path):
    path, records = library(
        tmp_path, {f"session-{i}": ["不做云同步", "Understood."] for i in range(6)}
    )
    result = select_evidence(path, max_chars=10_000)
    assert {r.evidence_id for r in result.records} == {r.evidence_id for r in records}
    assert result.coverage_complete and result.omitted_records == 0


def test_conversation_limit_is_visible_not_a_false_full_read(tmp_path):
    path, records = library(
        tmp_path, {f"session-{i}": ["Keep this whole conversation. " * 5] for i in range(3)}
    )
    result = select_evidence(path, per_source=1, max_chars=10_000)
    assert len(result.records) == 1
    assert not result.coverage_complete
    assert len(result.deferred_conversations) == 2
    assert result.omitted_records == len(records) - 1


def test_first_discover_waits_for_normal_source_import_before_selection(tmp_path, monkeypatch):
    async def scenario():
        home = tmp_path / "source-home"
        root = home / ".codex/sessions"
        root.mkdir(parents=True)
        texts = [f"Unrelated turn {i}" for i in range(39)]
        texts[19] = "The main requirement is in the middle, not the beginning or end. " * 12
        for session in range(3):
            path = root / f"rollout-random-{session}.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "type": "response_item",
                            "timestamp": (
                                datetime(2026, 9, 1, tzinfo=UTC) + timedelta(seconds=i)
                            ).isoformat(),
                            "payload": {
                                "type": "message",
                                "role": "user" if i % 2 else "assistant",
                                "content": [{"type": "input_text", "text": text}],
                            },
                        }
                    )
                    for i, text in enumerate(texts)
                )
                + "\n"
            )
        catalog = build_source_catalog(home=home, environment={})
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("test-only"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            ),
            source_catalog={"codex": catalog["codex"]},
            secret_store=InMemorySecretStore(),
        )
        async with app.router.lifespan_context(app):
            seen = []

            async def capture(records, **kwargs):
                seen.extend(records)
                raise ValueError("matter_stop_after_collection")

            monkeypatch.setattr(app.state.memory_processing_supervisor, "process_records", capture)
            from types import SimpleNamespace

            monkeypatch.setattr(
                app.state.matter_discovery.model,
                "profile",
                lambda *args: SimpleNamespace(profile_id="test", revision=1),
            )
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test-only"},
            ) as client:
                assert app.state.evidence_store.count() == 0
                authorized = await client.post(
                    "/api/v1/sources/codex/authorize",
                    json=await authorized_request(client, "codex"),
                )
                assert authorized.status_code == 200
                app.state.config_store.set_sync("codex", True)
                response = await client.post("/api/v1/matters/discover", json={})
                assert response.status_code == 202
                await asyncio.gather(*tuple(app.state.matter_discovery.tasks))
                assert len(seen) == 3 * len(texts)
                assert sum(record.verbatim == texts[19].strip() for record in seen) == 3
                runs = (await client.get("/api/v1/matters/runs")).json()
                assert runs[0]["import_job_ids"]
                assert runs[0]["coverage_complete"] is True
                assert runs[0]["error"] == "matter_stop_after_collection"
                assert app.state.evidence_store.count() == len(seen)

    asyncio.run(scenario())


@pytest.mark.parametrize("condition", ["paused", "failed", "unavailable", "malformed"])
def test_incomplete_import_never_reaches_hy_or_claims_full_coverage(
    tmp_path, monkeypatch, condition
):
    async def scenario():
        from types import SimpleNamespace

        home = tmp_path / "home"
        root = home / ".codex/sessions"
        root.mkdir(parents=True)
        if condition == "malformed":
            (root / "rollout-malformed.jsonl").write_text("invalid json\n")
        registration = build_source_catalog(home=home, environment={})["codex"]
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=home,
                api_token=SecretStr("test-only"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
            ),
            source_catalog={"codex": registration},
            secret_store=InMemorySecretStore(),
        )
        async with app.router.lifespan_context(app):
            monkeypatch.setattr(
                app.state.matter_discovery.model,
                "profile",
                lambda *args: SimpleNamespace(profile_id="test", revision=1),
            )

            async def forbidden(*args, **kwargs):
                pytest.fail("HY must not see an incompletely collected source")

            monkeypatch.setattr(
                app.state.memory_processing_supervisor, "process_records", forbidden
            )
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test-only"},
            ) as client:
                authorized = await client.post(
                    "/api/v1/sources/codex/authorize",
                    json=await authorized_request(client, "codex"),
                )
                assert authorized.status_code == 200
                app.state.config_store.set_sync("codex", True)
                if condition in {"paused", "failed"}:
                    job = app.state.import_job_store.create(user_id="local", source_id="codex")
                    if condition == "failed":
                        app.state.import_job_store.claim(job.job_id)
                    app.state.import_job_store.transition(job.job_id, ImportStatus(condition))
                elif condition == "unavailable":
                    app.state.import_supervisor.unregister_adapter("codex")
                assert (await client.post("/api/v1/matters/discover", json={})).status_code == 202
                await asyncio.gather(*tuple(app.state.matter_discovery.tasks))
                result = (await client.get("/api/v1/matters/runs")).json()[0]
                assert result["status"] == "failed"
                assert result["coverage_complete"] is False
                assert result["error"].startswith("matter_import_")
                assert app.state.matter_store.list() == []

    asyncio.run(scenario())
