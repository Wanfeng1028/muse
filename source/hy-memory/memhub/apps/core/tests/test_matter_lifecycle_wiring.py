"""The composition root must give MatterStore a live HY lifecycle source.

EXEC-1914-C3: production constructed `MatterStore(database_path)` with no
`lifecycle_source`, so a formal dossier was validated against the ledger mirror
alone and could keep serving a conclusion for a memory HY had already set
aside. This file pins the composition wiring itself:

  * production injects a source exposing `lifecycle_now`;
  * the source caches one bridge, because a per-read bridge is a fresh
    client/config lifecycle that could observe a different not-open state;
  * **EXEC-1914-MATTER-LIFECYCLE-BEHAVIOR-GUARD**: the composed `create_app`
    artifact - not just a hand-built `LifecycleSource` - actually invalidates a
    dossier when HY reports a cited memory hidden, and fails closed when the HY
    read is unreadable. Before this guard, a mutation that always reported
    "nothing hidden" passed every wiring test because they only asserted
    presence and caching.
"""

from __future__ import annotations

import asyncio
from hashlib import sha256

from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.hy_lifecycle import HyLifecycle, HyLifecycleUnreadable
from one_memory.hy_memory_bridge import HyMemoryIngestResult, HyMemoryOutput
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.sources.registry import RootCandidateKind
from one_memory.imports.storage import EvidenceStore
from one_memory.matters.models import Citation, Claim, MatterDraft, MemoryRef
from one_memory.memory_governance import MemoryGovernanceStore
from one_memory.memory_processing import MemoryProcessingSupervisor, _conversation_chunks
from one_memory.memory_tasks import MemoryTaskStore
from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileInput,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore


class _Bridge:
    async def ingest(self, request):
        return HyMemoryIngestResult(
            success=True,
            memories=(
                HyMemoryOutput(
                    memory_id="hy-atlas",
                    content="Atlas only local.",
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


class _Hidden:
    """A lifecycle view that reports the cited memory hidden."""

    def __init__(self, ids):
        self._ids = set(ids)

    def lifecycle_now(self, _user_id, memory_ids):
        return HyLifecycle(hidden={i: () for i in memory_ids if i in self._ids})


class _Unreadable:
    """HY cannot be read: must fail closed, never read as "nothing hidden"."""

    def lifecycle_now(self, _user_id, _memory_ids):
        raise HyLifecycleUnreadable("hy_lifecycle_unreadable")


class _NothingHidden:
    def lifecycle_now(self, _user_id, _memory_ids):
        return HyLifecycle()


def _settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        source_home=tmp_path,
        api_token=SecretStr("matter-lifecycle"),
        imports_enabled=False,
        automatic_memory_processing=True,
        live_sync_enabled=False,
    )


def _application(tmp_path):
    return create_app(_settings(tmp_path), secret_store=InMemorySecretStore())


def test_production_matter_store_has_a_lifecycle_source(tmp_path) -> None:
    async def scenario() -> None:
        app = _application(tmp_path)
        async with app.router.lifespan_context(app):
            source = app.state.matter_store._lifecycle_source  # noqa: SLF001
            assert source is not None, (
                "production MatterStore must be built with a lifecycle source"
            )
            assert callable(getattr(source, "lifecycle_now", None))
            # Two reads must reuse one bridge: a per-read construction is a
            # different client/config lifecycle and is exactly the defect the
            # C3 review caught.
            first = source._lifecycle_bridge()  # noqa: SLF001
            second = source._lifecycle_bridge()  # noqa: SLF001
            assert first is second, "the lifecycle bridge must be cached, not rebuilt"

    asyncio.run(scenario())


def _seed_memory(tmp_path) -> None:
    """Write one completed hy-memory task/row so a MemoryRef can validate.

    Uses the real processing supervisor, so the ledger row, the task row and
    the output body all match what `MatterStore._valid_memory_ref` requires.
    """
    path = tmp_path / "data" / "one-memory.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
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
            verbatim="Atlas only local.",
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
            verbatim="Acknowledged.",
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
        bridge_factory=lambda *_: _Bridge(),
    )

    async def run():
        try:
            conversation = processor.evidence.list_conversation(record.evidence_id)
            (turn,) = _conversation_chunks(conversation, completed_only=True)
            created = await processor.process_records(turn, profile_id=profile.profile_id)
            output = processor.tasks.outputs(created[0].task_id)[0]
            memory = processor.governance.get(output.memory_id, user_id="local")
            return output, memory, record, created[0]
        finally:
            await processor.shutdown()

    output, memory, record, task = asyncio.run(run())
    return output, memory, record, task


def _save_dossier(app, output, memory, record, task) -> str:
    ref = MemoryRef(
        memory_id=memory.memory_id,
        revision=memory.revision,
        status=memory.status,
        content_hash=sha256(memory.content.encode()).hexdigest(),
        task_id=output.task_id,
        hy_memory_id=output.hy_memory_id,
        engine_version=output.engine_version,
        profile_id=task.profile_id,
        profile_revision=task.profile_revision,
        model=task.profile_snapshot.model,
    )
    claim = Claim(
        statement=memory.content,
        kind="constraint",
        citations=[Citation(evidence_id=record.evidence_id, quote=memory.content)],
        memory_refs=[ref],
    )
    saved = app.state.matter_store.save(
        MatterDraft(
            title="Atlas notes",
            purpose="delivery",
            boundary="Atlas",
            claims=[claim],
            anchors=[record.evidence_id],
        ),
        model="test-model",
        require_hy=True,
    )
    return saved.matter_id, memory.memory_id


def test_composed_app_invalidates_hidden_memory_and_fails_closed(tmp_path) -> None:
    """The composed artifact itself must honour HY's lifecycle.

    Positive control (`_NothingHidden`) proves the dossier is otherwise
    available, so the two negative cases cannot pass by being broken some other
    way. This is the red/green that `EXEC-1914-MATTER-LIFECYCLE-BEHAVIOR-GUARD`
    asked for: a mutation returning an empty `HyLifecycle` from the composed
    source must turn the hidden case red.
    """
    output, memory, record, task = _seed_memory(tmp_path)

    async def scenario() -> None:
        app = _application(tmp_path)
        async with app.router.lifespan_context(app):
            store = app.state.matter_store
            matter_id, memory_id = _save_dossier(app, output, memory, record, task)

            # Positive control: nothing hidden -> the dossier stays available.
            store._lifecycle_source = _NothingHidden()  # noqa: SLF001
            assert store.get(matter_id).availability == "ready"

            # HY reports the cited memory hidden -> the dossier must invalidate.
            store._lifecycle_source = _Hidden({memory_id})  # noqa: SLF001
            hidden = store.get(matter_id)
            assert hidden.availability == "memory_changed"
            assert hidden.claims == []

            # HY cannot be read -> fail closed, not "nothing hidden".
            store._lifecycle_source = _Unreadable()  # noqa: SLF001
            unreadable = store.get(matter_id)
            assert unreadable.availability == "memory_changed"
            assert unreadable.claims == []

    asyncio.run(scenario())
