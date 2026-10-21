import asyncio
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from one_memory.hy_memory_bridge import HyMemoryBridgeError, HyMemoryIngestResult, HyMemoryOutput
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.sources.registry import RootCandidateKind
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import MemoryGovernanceStore
from one_memory.memory_processing import MemoryProcessingSupervisor, _conversation_chunks
from one_memory.memory_server.durable_queue import (
    DurableWriteDrain,
    DurableWriteQueue,
    execute_job,
)
from one_memory.memory_server.unified_entry import UnifiedWriteIntake
from one_memory.memory_tasks import MemoryTaskStatus, MemoryTaskStore
from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileInput,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore, KeyringSecretStore
from tests.person_door import as_person


class Bridge:
    def __init__(self, fail=False):
        self.fail = fail
        self.requests = []

    async def ingest(self, request):
        self.requests.append(request)
        if self.fail:
            raise HyMemoryBridgeError("hy_memory_unavailable")
        return HyMemoryIngestResult(
            success=True,
            memories=(
                HyMemoryOutput(
                    memory_id="hy-atlas",
                    content="Atlas仅在本机保存资料。",
                    owner="user",
                    layer="L2_FACT",
                    tags=("Atlas",),
                ),
            ),
        )

    async def profile_memories(self, **kwargs):
        return ()

    async def close(self):
        pass


def setup(tmp_path, bridge):
    path = tmp_path / "one-memory.sqlite3"
    evidence, profiles = EvidenceStore(path), ModelProfileStore(path)
    tasks, governance = MemoryTaskStore(path), MemoryGovernanceStore(path)
    secrets = InMemorySecretStore()
    profile = profiles.create(
        ModelProfileInput(
            name="test",
            provider_kind=ProviderKind.OLLAMA,
            model="test-model",
            disable_thinking=True,
        ),
        secrets,
    )
    profiles.record_capabilities(
        profile.profile_id,
        expected_revision=1,
        secrets=secrets,
        capabilities=ModelCapabilities(
            endpoint_reachable=True, model_available=True, embedding_available=True
        ),
    )
    profile = profiles.activate(profile.profile_id, secrets)
    grants = SourceGrantStore(path, home=tmp_path)
    grants.grant(
        user_id="local",
        source_id="cursor",
        root=tmp_path,
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    record = evidence.put(
        EvidenceInput(
            source_id="cursor",
            conversation_id="atlas",
            message_id="u1",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim="Atlas仅在本机保存资料。目标是交付一个本地笔记工具。",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    evidence.put(
        EvidenceInput(
            source_id="cursor",
            conversation_id="atlas",
            message_id="a1",
            role="assistant",
            written_by=WrittenBy.AGENT,
            verbatim="收到，我会按这个要求继续整理。",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    )
    processor = MemoryProcessingSupervisor(
        tasks=tasks,
        profiles=profiles,
        secrets=secrets,
        evidence=evidence,
        governance=governance,
        data_dir=tmp_path,
        bridge_factory=lambda *_: bridge,
    )
    return processor, record, profile


def queued_discovery(service, processor):
    queue = DurableWriteQueue(
        processor.tasks.database_path,
        evidence=processor.evidence,
    )
    service.write_queue = queue
    service.write_intake = UnifiedWriteIntake(queue)
    drain = DurableWriteDrain(
        queue,
        execute=lambda job_id: execute_job(
            job_id,
            queue=queue,
            supervisor=processor,
            evidence=processor.evidence,
        ),
    )
    return drain


def complete_turn(processor, record):
    """Return the settled turn containing ``record`` under the current ingest contract."""
    conversation = processor.evidence.list_conversation(record.evidence_id)
    matches = [
        chunk
        for chunk in _conversation_chunks(conversation, completed_only=True)
        if any(item.evidence_id == record.evidence_id for item in chunk)
    ]
    assert len(matches) == 1, (record.evidence_id, matches)
    return matches[0]


async def process_turn(processor, record, **kwargs):
    return await processor.process_records(complete_turn(processor, record), **kwargs)


def test_hy_inputs_are_frozen_and_outputs_keep_task_and_governance_links(tmp_path):
    async def scenario():
        bridge = Bridge()
        processor, record, profile = setup(tmp_path, bridge)
        try:
            tasks = await process_turn(processor, record, profile_id=profile.profile_id)
            assert len(tasks) == 1 and tasks[0].status is MemoryTaskStatus.COMPLETED
            assert bridge.requests[0].turns[0].content == record.verbatim
            inputs = processor.tasks.inputs(tasks[0].task_id)
            assert inputs[0]["evidence_id"] == record.evidence_id
            outputs = processor.tasks.outputs(tasks[0].task_id)
            assert outputs[0].memory_id == "hy-atlas"
            assert outputs[0].engine == "hy-memory"
            assert outputs[0].hy_memory_id == "hy-atlas"
            assert processor.governance.get(outputs[0].memory_id, user_id="local") is not None
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_history_supported_repeat_does_not_reassign_its_source_to_new_assistant_turn(tmp_path):
    from test_hy_source_context import source

    class SupportedBridge(Bridge):
        async def ingest(self, request):
            self.requests.append(request)
            original = (request.source_context.history or request.source_context.current)[0]
            return HyMemoryIngestResult(
                success=True,
                memories=(
                    HyMemoryOutput(
                        memory_id="hy-atlas",
                        content="Atlas仅在本机保存资料。",
                        owner="user",
                        layer="L2_FACT",
                        evidence_ids=(original.evidence_id,),
                    ),
                ),
            )

    async def scenario():
        bridge = SupportedBridge()
        processor, old, _ = setup(tmp_path, bridge)
        later = source(processor.evidence, "later", "assistant", "我继续整理。")
        source(processor.evidence, "later-adopt", "user", "好，继续。")
        try:
            await process_turn(processor, old)
            await process_turn(processor, later)
            memory = processor.governance.get("hy-atlas", user_id="local")
            assert memory.evidence_ids == (old.evidence_id,)
            assert memory.origin.value == "extracted", (
                "Historical user support does not become Agent-owned"
            )
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_bound_native_update_preserves_memory_identity_revision_and_source_union(tmp_path):
    from test_hy_source_context import source

    class UpdatingBridge(Bridge):
        async def ingest(self, request):
            self.requests.append(request)
            records = (*request.source_context.history, *request.source_context.current)
            return HyMemoryIngestResult(
                success=True,
                memories=(
                    HyMemoryOutput(
                        memory_id="hy-atlas",
                        content="Atlas仅在本机保存资料。"
                        + ("日志保留30天。" if len(self.requests) > 1 else ""),
                        owner="user",
                        layer="L2_FACT",
                        evidence_ids=tuple(r.evidence_id for r in records),
                    ),
                ),
            )

    async def scenario():
        bridge = UpdatingBridge()
        processor, old, _ = setup(tmp_path, bridge)
        later = source(processor.evidence, "later", "user", "日志保留30天。")
        source(processor.evidence, "later-reply", "assistant", "已记录日志策略。")
        try:
            await process_turn(processor, old)
            first = processor.governance.get("hy-atlas", user_id="local")
            await process_turn(processor, later)
            current = processor.governance.get("hy-atlas", user_id="local")
            assert current.revision == first.revision + 1
            assert current.content == "Atlas仅在本机保存资料。日志保留30天。"
            assert set(current.evidence_ids) == {
                record.evidence_id
                for record in (*complete_turn(processor, old), *complete_turn(processor, later))
            }
            history = processor.governance.history("hy-atlas", user_id="local")
            assert any(version.content == first.content for version in history)
            newest = source(processor.evidence, "newest", "assistant", "我继续整理。")
            source(processor.evidence, "newest-adopt", "user", "继续。")
            await process_turn(processor, newest)
            context = bridge.requests[-1].source_context
            assert old.evidence_id in {record.evidence_id for record in context.history}
            assert context.known_memories[0].revision == current.revision
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("entry", ["assemble", "read"])
def test_old_hy_task_cannot_certify_a_new_governed_memory_revision(tmp_path, entry):
    from hashlib import sha256

    from one_memory.matters.hy_source import governed_outputs
    from one_memory.matters.store import MatterStore

    async def scenario():
        processor, record, _ = setup(tmp_path, Bridge())
        try:
            tasks = await process_turn(processor, record)
            memories, refs = governed_outputs(processor, tasks)
            memory = memories["hy-atlas"]
            changed = as_person(processor.governance).correct(
                memory.memory_id,
                user_id="local",
                request_id="human-edit",
                expected_revision=memory.revision,
                content="用户已人工更正这条记忆。",
            )
            if entry == "assemble":
                assert governed_outputs(processor, tasks) == ({}, {})
            else:
                ref = refs[memory.memory_id].model_copy(
                    update={
                        "revision": changed.revision,
                        "content_hash": sha256(changed.content.encode()).hexdigest(),
                    }
                )
                store = MatterStore(processor.tasks.database_path)
                with store._connect() as db:
                    assert not store._valid_memory_ref(db, ref)
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_hy_failure_never_becomes_a_successful_extraction(tmp_path):
    async def scenario():
        processor, record, profile = setup(tmp_path, Bridge(fail=True))
        try:
            with pytest.raises(HyMemoryBridgeError, match="hy_memory_unavailable"):
                await process_turn(processor, record, profile_id=profile.profile_id)
            assert processor.governance.list(user_id="local") == []
            task = processor.tasks.list()[0]
            assert task.status is MemoryTaskStatus.WAITING_FOR_MODEL
            assert processor.tasks.outputs(task.task_id) == ()
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_timeline_precedes_writing_without_replacing_the_hy_reference(tmp_path, monkeypatch):
    from one_memory.matters.discovery import MatterDiscovery
    from one_memory.matters.models import DiscoveryInput
    from one_memory.matters.store import MatterStore

    async def scenario():
        processor, record, profile = setup(tmp_path, Bridge())
        trace = []

        class Model:
            def profile(self, *_):
                return profile

            async def complete(self, system, data, **kwargs):
                if "memories" in data:
                    return {
                        "items": [
                            {
                                "memory_id": "hy-atlas",
                                "matter_title": "Atlas",
                                "kind": "constraint",
                                "state": "current",
                                "citations": [
                                    {
                                        "evidence_id": record.evidence_id,
                                        "quote": "Atlas仅在本机保存资料。",
                                    }
                                ],
                            }
                        ]
                    }
                if "segments" in data:
                    return {
                        "matters": [
                            {
                                "title": "Atlas",
                                "purpose": "Local notes",
                                "boundary": "Atlas product",
                                "claim_ids": data["allowed_claim_ids"],
                            }
                        ]
                    }
                return {
                    "reviews": [
                        {"id": claim["id"], "verdict": "supported"} for claim in data["claims"]
                    ]
                }

        async def timeline(_model, draft, governed, _records, **kwargs):
            trace.append("timeline")
            assert draft.claims[0].statement == "Atlas仅在本机保存资料。"
            return draft.model_copy(
                update={"claims": [draft.claims[0].model_copy(update={"state": "historical"})]}
            )

        async def write(_model, draft, _records, *, context=None, **kwargs):
            assert trace == ["timeline"]
            trace.append("write")
            assert draft.claims[0].state == "historical"
            assert context.claims[0].state == "current"
            assert context.claims[0].statement == "Atlas仅在本机保存资料。"
            return draft, 0

        monkeypatch.setattr("one_memory.matters.discovery.reconcile_governed_timeline", timeline)
        monkeypatch.setattr("one_memory.matters.discovery.synthesize", write)
        store = MatterStore(processor.evidence.database_path)
        try:
            service = MatterDiscovery(store, Model(), processor)
            drain = queued_discovery(service, processor)
            worker = asyncio.create_task(drain.run_forever(idle_pause=0.005))
            result = await service.run(DiscoveryInput())
            drain.stop()
            await worker
            assert result.status == "completed", result
            assert trace == ["timeline", "write"]
            assert (
                processor.governance.get("hy-atlas", user_id="local").content
                == "Atlas仅在本机保存资料。"
            )
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_changed_evidence_is_rebuilt_from_the_current_snapshot(tmp_path):
    async def scenario():
        bridge = Bridge()
        processor, record, profile = setup(tmp_path, bridge)
        try:
            processor.evidence.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="atlas",
                    message_id="u1",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="Correction: Atlas will not ship yet.",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            )
            tasks = await process_turn(processor, record, profile_id=profile.profile_id)
            assert len(tasks) == 1 and tasks[0].status is MemoryTaskStatus.COMPLETED
            assert bridge.requests[0].turns[0].content == "Correction: Atlas will not ship yet."
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_task_and_frozen_inputs_commit_atomically(tmp_path):
    processor, record, profile = setup(tmp_path, Bridge())
    with sqlite3.connect(processor.tasks.database_path) as db:
        db.execute(
            "CREATE TRIGGER fail_input BEFORE INSERT ON memory_task_inputs "
            "BEGIN SELECT RAISE(ABORT, 'snapshot write failed'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="snapshot write failed"):
        processor._enqueue_chunk((record,), profile, freeze_inputs=True)
    assert processor.tasks.list() == []


def test_replaying_completed_snapshot_does_not_extract_twice(tmp_path):
    async def scenario():
        bridge = Bridge()
        processor, record, profile = setup(tmp_path, bridge)
        try:
            first = await process_turn(processor, record, profile_id=profile.profile_id)
            second = await process_turn(processor, record, profile_id=profile.profile_id)
            assert first[0].task_id == second[0].task_id
            assert len(bridge.requests) == 1
            assert len(processor.tasks.outputs(first[0].task_id)) == 1
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_invalid_classification_reference_has_one_scoped_retry(tmp_path, repair_succeeds):
    from one_memory.matters.hy_source import classify_memories, governed_outputs
    from one_memory.matters.store import MatterStore

    async def scenario():
        processor, record, _ = setup(tmp_path, Bridge())
        try:
            tasks = await process_turn(processor, record)
            memories, refs = governed_outputs(processor, tasks)
            store = MatterStore(processor.tasks.database_path)
            with store._connect() as db:
                sample = store._source(db, record.evidence_id)

            class Classifier:
                calls = 0

                async def complete(self, system, data, **kwargs):
                    self.calls += 1
                    if self.calls == 2:
                        assert [m["memory_id"] for m in data["memories"]] == ["hy-atlas"]
                        assert [e["evidence_id"] for e in data["evidence"]] == [record.evidence_id]
                    return {
                        "items": [
                            {
                                "memory_id": "hy-atlas",
                                "matter_title": "Atlas笔记",
                                "kind": "constraint",
                                "state": "current",
                                "citations": [
                                    {
                                        "evidence_id": record.evidence_id
                                        if self.calls == 2 and repair_succeeds
                                        else "unlinked-evidence",
                                        "quote": "Atlas仅在本机保存资料。",
                                    }
                                ],
                            }
                        ]
                    }

            model = Classifier()
            claims, _, rejected = await classify_memories(
                model, memories, refs, [sample], profile_id=None
            )
            assert model.calls == 2
            if repair_succeeds:
                assert claims["c0"].statement == memories["hy-atlas"].content
                assert claims["c0"].citations[0].evidence_id == record.evidence_id
                assert rejected == 0
            else:
                assert claims == {} and rejected == 1
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_default_discovery_cannot_bypass_hy_when_hy_fails(tmp_path, monkeypatch):
    from one_memory.matters.discovery import MatterDiscovery
    from one_memory.matters.model import MatterModel
    from one_memory.matters.models import DiscoveryInput
    from one_memory.matters.store import MatterStore
    async def scenario():
        processor, record, _ = setup(tmp_path, Bridge(fail=True))
        try:
            # Keep selection substantive; this is a fresh library with no old Wiki to reuse.
            processor.evidence.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="atlas",
                    message_id="u2",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="Atlas is a local note editor. " * 5,
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            )
            model = MatterModel(processor.profiles, processor.secrets)

            async def forbidden(*args, **kwargs):
                pytest.fail("Wiki model was called after HY extraction failed")

            monkeypatch.setattr(model, "complete", forbidden)
            store = MatterStore(processor.tasks.database_path)
            service = MatterDiscovery(store, model, processor)
            drain = queued_discovery(service, processor)
            worker = asyncio.create_task(drain.run_forever(idle_pause=0.005))
            result = await service.run(DiscoveryInput(max_chars=10_000))
            drain.stop()
            await worker
            assert result.status == "failed"
            assert result.error == "hy_memory_unavailable"
            assert store.list() == []
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_discovery_persists_elapsed_time_while_awaiting_the_model(tmp_path):
    from one_memory.matters.discovery import MatterDiscovery
    from one_memory.matters.model import MatterModel
    from one_memory.matters.models import DiscoveryInput
    from one_memory.matters.store import MatterStore

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        class WaitingBridge(Bridge):
            async def ingest(self, request):
                entered.set()
                await release.wait()
                return await super().ingest(request)

        processor, _, _ = setup(tmp_path, WaitingBridge())
        store = MatterStore(processor.tasks.database_path)
        service = MatterDiscovery(
            store, MatterModel(processor.profiles, processor.secrets), processor
        )
        drain = queued_discovery(service, processor)
        worker = asyncio.create_task(drain.run_forever(idle_pause=0.005))
        try:
            service.start(DiscoveryInput())
            await asyncio.wait_for(entered.wait(), timeout=5)
            before = store.runs()[0]
            await asyncio.sleep(1.15)
            current = store.runs()[0]
            assert current.status == "running" and current.phase == before.phase
            assert current.elapsed_seconds > before.elapsed_seconds
            assert current.completed_batches == 0
        finally:
            await service.shutdown()
            release.set()
            drain.stop()
            await worker
            await processor.shutdown()
        assert store.runs()[0].status == "interrupted"

    asyncio.run(scenario())


def test_classification_schema_repair_is_bounded_and_preserves_allowed_sources():
    from one_memory.matters.hy_source import _classify_batch

    class Model:
        calls = 0

        async def complete(self, system, data, **kwargs):
            self.calls += 1
            if self.calls == 2:
                assert data["evidence"] == [{"evidence_id": "e1", "text": "Original source."}]
                assert data["validation_errors"][0]["loc"] == ("items", 0, "citations")
            return {
                "items": [
                    {
                        "memory_id": "m1",
                        "matter_title": "Atlas",
                        "kind": "goal",
                        "citations": [{"evidence_id": "e1", "quote": "Original source."}]
                        * (9 if self.calls == 1 else 1),
                    }
                ]
            }

    model = Model()
    result = asyncio.run(
        _classify_batch(
            model,
            {
                "memories": [{"memory_id": "m1"}],
                "evidence": [{"evidence_id": "e1", "text": "Original source."}],
            },
            profile_id=None,
        )
    )
    assert model.calls == 2 and len(result.items[0].citations) == 1


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_duplicate_classification_ids_receive_one_repair_not_silent_deduplication(repair_succeeds):
    from one_memory.matters.hy_source import _classify_batch

    class Model:
        calls = 0

        async def complete(self, system, data, **kwargs):
            self.calls += 1
            item = {
                "memory_id": "m1",
                "matter_title": "Atlas",
                "kind": "goal",
                "citations": [{"evidence_id": "e1", "quote": "Original."}],
            }
            if self.calls == 2:
                assert data["validation_errors"][0]["type"] == "matter_hy_classification_invalid_id"
            return {"items": [item] if self.calls == 2 and repair_succeeds else [item, item]}

    model = Model()
    task = _classify_batch(model, {"memories": [{"memory_id": "m1"}]}, profile_id=None)
    if repair_succeeds:
        assert len(asyncio.run(task).items) == 1
    else:
        with pytest.raises(ValueError, match="classification_invalid_id"):
            asyncio.run(task)
    assert model.calls == 2


def test_context_grounding_finds_prior_support_without_crossing_conversation_scope(tmp_path):
    from one_memory.matters.hy_source import classify_memories, governed_outputs
    from one_memory.matters.store import MatterStore

    async def scenario():
        processor, original, _ = setup(tmp_path, Bridge())
        try:
            current = processor.evidence.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="atlas",
                    message_id="later",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="Continue the earlier discussion.",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            processor.evidence.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="atlas",
                    message_id="later-reply",
                    role="assistant",
                    written_by=WrittenBy.AGENT,
                    verbatim="Continuing the earlier discussion.",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            )
            unrelated = processor.evidence.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="other",
                    message_id="other",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="An unrelated project.",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            tasks = await process_turn(processor, current)
            memories, refs = governed_outputs(processor, tasks)
            assert original.evidence_id not in memories["hy-atlas"].evidence_ids
            store = MatterStore(processor.tasks.database_path)
            with store._connect() as db:
                records = [store._source(db, r.evidence_id) for r in (original, current, unrelated)]

            class Model:
                async def complete(self, system, data, **kwargs):
                    allowed = data["memories"][0]["evidence_ids"]
                    assert original.evidence_id in allowed
                    assert current.evidence_id in allowed
                    assert unrelated.evidence_id not in allowed
                    return {
                        "items": [
                            {
                                "memory_id": "hy-atlas",
                                "matter_title": "Atlas",
                                "kind": "constraint",
                                "state": "current",
                                "citations": [
                                    {
                                        "evidence_id": original.evidence_id,
                                        "quote": "Atlas仅在本机保存资料。",
                                    }
                                ],
                            }
                        ]
                    }

            claims, _, rejected = await classify_memories(
                Model(), memories, refs, records, profile_id=None, recover_context=True
            )
            assert rejected == 0
            assert claims["c0"].statement == memories["hy-atlas"].content
            assert claims["c0"].citations[0].evidence_id == original.evidence_id
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_semantic_repair_only_changes_metadata_and_is_independently_rechecked(
    tmp_path, repair_succeeds
):
    from one_memory.matters.discovery import MatterDiscovery
    from one_memory.matters.hy_source import classify_memories, governed_outputs
    from one_memory.matters.store import MatterStore

    async def scenario():
        processor, record, _ = setup(tmp_path, Bridge())
        try:
            tasks = await process_turn(processor, record)
            memories, refs = governed_outputs(processor, tasks)
            store = MatterStore(processor.tasks.database_path)
            with store._connect() as db:
                sample = store._source(db, record.evidence_id)

            class Model:
                checks = 0
                repairs = 0

                async def complete(self, system, data, **kwargs):
                    if "memories" in data:
                        if data.get("review_notes"):
                            self.repairs += 1
                            assert list(data["review_notes"]) == ["hy-atlas"]
                        return {
                            "items": [
                                {
                                    "memory_id": "hy-atlas",
                                    "matter_title": "Atlas",
                                    "kind": "proposal" if self.repairs else "decision",
                                    "state": "current",
                                    "citations": [
                                        {
                                            "evidence_id": record.evidence_id,
                                            "quote": "Atlas仅在本机保存资料。",
                                        }
                                    ],
                                }
                            ]
                        }
                    self.checks += 1
                    assert data["claims"][0]["statement"] == memories["hy-atlas"].content
                    return {
                        "reviews": [
                            {
                                "id": "c0",
                                "verdict": "supported"
                                if self.checks == 2 and repair_succeeds
                                else "uncertain",
                                "reason": "This expresses a proposal, not an adopted decision.",
                            }
                        ]
                    }

            model = Model()
            claims, segments, _ = await classify_memories(
                model, memories, refs, [sample], profile_id=None
            )
            service = MatterDiscovery(store, model, processor)
            accepted, _ = await service._review_and_repair(
                claims, segments, memories, refs, [sample], profile_id=None
            )
            assert model.checks == 2 and model.repairs == 1
            if repair_succeeds:
                assert accepted["c0"].kind == "proposal"
                assert accepted["c0"].statement == memories["hy-atlas"].content
            else:
                assert accepted == {}
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["delete", "correct"])
def test_formal_dossier_invalidates_on_governance_change(tmp_path, operation):
    from hashlib import sha256

    from one_memory.hy_lifecycle import HyLifecycle
    from one_memory.matters.models import Citation, Claim, MatterDraft, MatterPatch, MemoryRef
    from one_memory.matters.store import MatterStore
    from one_memory.memory_governance import MemoryStatus

    class NothingHidden:
        def lifecycle_now(self, _user_id, memory_ids):
            return HyLifecycle(hidden={})

    async def scenario():
        processor, record, _ = setup(tmp_path, Bridge())
        try:
            tasks = await process_turn(processor, record)
            output = processor.tasks.outputs(tasks[0].task_id)[0]
            memory = processor.governance.get(output.memory_id, user_id="local")
            ref = MemoryRef(
                memory_id=memory.memory_id,
                revision=memory.revision,
                status=memory.status,
                content_hash=sha256(memory.content.encode()).hexdigest(),
                task_id=output.task_id,
                hy_memory_id=output.hy_memory_id,
                engine_version=output.engine_version,
                profile_id=tasks[0].profile_id,
                profile_revision=tasks[0].profile_revision,
                model=tasks[0].profile_snapshot.model,
            )
            claim = Claim(
                statement=memory.content,
                kind="constraint",
                citations=[
                    Citation(evidence_id=record.evidence_id, quote="Atlas仅在本机保存资料。")
                ],
                memory_refs=[ref],
            )
            store = MatterStore(
                processor.tasks.database_path,
                lifecycle_source=NothingHidden(),
            )
            saved = store.save(
                MatterDraft(
                    title="Atlas笔记开发",
                    purpose="交付笔记",
                    boundary="Atlas",
                    claims=[claim],
                    anchors=[record.evidence_id],
                ),
                model="test-model",
                require_hy=True,
            )
            assert saved.source_engine == "hy-memory"
            assert store.search_contexts("Atlas") == []
            saved = store.patch(
                saved.matter_id, MatterPatch(expected_version=saved.version, scope_confirmed=True)
            )
            assert store.search_contexts("Atlas") == []
            store.patch(
                saved.matter_id, MatterPatch(expected_version=saved.version, agent_access=True)
            )
            assert len(store.search_contexts("Atlas")) == 1
            if operation == "delete":
                as_person(processor.governance).delete(
                    memory.memory_id,
                    user_id="local",
                    request_id="delete",
                    expected_revision=memory.revision,
                )
            else:
                as_person(processor.governance).correct(
                    memory.memory_id,
                    user_id="local",
                    request_id="correct",
                    expected_revision=memory.revision,
                    content="Atlas的存储方案尚未确定。",
                    scopes=memory.scopes,
                )
            stale = store.get(saved.matter_id)
            assert stale.availability == "memory_changed"
            assert stale.claims == []
            assert "Atlas" not in store.context(saved.matter_id).text
            if operation == "delete":
                assert (
                    processor.governance.get(memory.memory_id, user_id="local").status
                    is MemoryStatus.DELETED
                )
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


def test_formal_dossier_consumes_hy_lifecycle_not_only_the_ledger_mirror(tmp_path):
    """A hidden HY node invalidates the derived claim even before ledger writeback."""
    from hashlib import sha256

    from one_memory.hy_lifecycle import HyLifecycle
    from one_memory.matters.models import Citation, Claim, MatterDraft, MemoryRef
    from one_memory.matters.store import MatterStore

    class LifecycleSource:
        def __init__(self, hidden):
            self.hidden = hidden

        def lifecycle_now(self, _user_id, memory_ids):
            return HyLifecycle(
                hidden={memory_id: () for memory_id in memory_ids if memory_id in self.hidden}
            )

    async def scenario():
        processor, record, _ = setup(tmp_path, Bridge())
        try:
            tasks = await process_turn(processor, record)
            output = processor.tasks.outputs(tasks[0].task_id)[0]
            memory = processor.governance.get(output.memory_id, user_id="local")
            ref = MemoryRef(
                memory_id=memory.memory_id,
                revision=memory.revision,
                status=memory.status,
                content_hash=sha256(memory.content.encode()).hexdigest(),
                task_id=output.task_id,
                hy_memory_id=output.hy_memory_id,
                engine_version=output.engine_version,
                profile_id=tasks[0].profile_id,
                profile_revision=tasks[0].profile_revision,
                model=tasks[0].profile_snapshot.model,
            )
            claim = Claim(
                statement=memory.content,
                kind="constraint",
                citations=[
                    Citation(evidence_id=record.evidence_id, quote="Atlas仅在本机保存资料。")
                ],
                memory_refs=[ref],
            )
            store = MatterStore(
                processor.tasks.database_path,
                lifecycle_source=LifecycleSource({output.memory_id}),
            )
            saved = store.save(
                MatterDraft(
                    title="Atlas笔记开发",
                    purpose="交付笔记",
                    boundary="Atlas",
                    claims=[claim],
                    anchors=[record.evidence_id],
                ),
                model="test-model",
                require_hy=True,
            )
            assert saved.source_engine == "hy-memory"
            hidden = store.get(saved.matter_id)
            assert hidden.availability == "memory_changed"
            assert hidden.claims == []
            # A new store instance represents a process restart: the stale
            # ledger body and model cache must not resurrect the claim.
            restarted = MatterStore(
                processor.tasks.database_path,
                lifecycle_source=LifecycleSource({output.memory_id}),
            )
            assert restarted.get(saved.matter_id).availability == "memory_changed"
            assert "Atlas" not in restarted.get(saved.matter_id).model_dump_json()
        finally:
            await processor.shutdown()

    asyncio.run(scenario())


@pytest.mark.skipif(
    not os.environ.get("ONE_MEMORY_MODEL_TEST_DB"), reason="explicit provider required"
)
def test_real_hy_sdk_extracts_governed_memory_with_configured_strong_model(tmp_path, monkeypatch):
    from hy_memory.client import HyMemoryClient

    calls = []
    original_add = HyMemoryClient.add

    def measured_add(self, data, **kwargs):
        calls.append({"request_id": kwargs["request_id"], "turns": len(data)})
        return original_add(self, data, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Raw evidence must not use add_extracted")

    monkeypatch.setattr(HyMemoryClient, "add", measured_add)
    monkeypatch.setattr(HyMemoryClient, "add_extracted", forbidden)

    async def scenario():
        database = tmp_path / "one-memory.sqlite3"
        evidence, profiles = EvidenceStore(database), ModelProfileStore(database)
        tasks, governance = MemoryTaskStore(database), MemoryGovernanceStore(database)
        with (
            sqlite3.connect(
                Path(os.environ["ONE_MEMORY_MODEL_TEST_DB"]).as_uri() + "?mode=ro", uri=True
            ) as src,
            sqlite3.connect(database) as db,
        ):
            src.row_factory = sqlite3.Row
            for table in ("model_profiles", "model_profile_versions"):
                fields = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
                for row in src.execute(f"SELECT * FROM {table}"):
                    keys = [key for key in dict(row) if key in fields]
                    db.execute(
                        f"INSERT INTO {table} ({','.join(keys)}) "
                        f"VALUES ({','.join('?' for _ in keys)})",
                        [row[key] for key in keys],
                    )
        grants = SourceGrantStore(database, home=tmp_path)
        grants.grant(
            user_id="local",
            source_id="fixture",
            root=tmp_path,
            candidate_kind=RootCandidateKind.DEFAULT,
        )
        records = tuple(
            evidence.put(
                EvidenceInput(
                    source_id="fixture",
                    conversation_id="atlas",
                    message_id=f"m{i}",
                    role=role,
                    written_by=author,
                    workspace="/projects/atlas",
                    created_at=datetime(2026, 9, 11, tzinfo=UTC),
                    verbatim=text,
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record
            for i, (role, author, text) in enumerate(
                [
                    (
                        "user",
                        WrittenBy.PERSON,
                        "我正在开发Atlas本地笔记产品，决定9月23日发布。第一版只做文本笔记，不做云同步。",
                    ),
                    (
                        "assistant",
                        WrittenBy.AGENT,
                        "我建议先验证本机保存与恢复，跨平台验收还没有做。",
                    ),
                    (
                        "user",
                        WrittenBy.PERSON,
                        "对，Atlas的资料必须默认保存在本机。不要把建议和已验收混在一起。",
                    ),
                ]
            )
        )
        processor = MemoryProcessingSupervisor(
            tasks=tasks,
            profiles=profiles,
            secrets=KeyringSecretStore(),
            evidence=evidence,
            governance=governance,
            data_dir=tmp_path,
        )
        try:
            result = await processor.process_records(records)
            assert calls and all(task.status is MemoryTaskStatus.COMPLETED for task in result)
            outputs = [output for task in result for output in tasks.outputs(task.task_id)]
            assert outputs, "Real HY returned no persisted memory output"
            memories = [governance.get(output.memory_id, user_id="local") for output in outputs]
            assert any("Atlas" in m.content for m in memories if m)
            assert all(output.engine == "hy-memory" and output.engine_version for output in outputs)
            assert all(
                m and set(m.evidence_ids).issubset({r.evidence_id for r in records})
                for m in memories
            )
        finally:
            await processor.shutdown()

    asyncio.run(scenario())
