"""A HY-backed Matter must fail closed when no lifecycle source is wired.

All three independent reviews of the generation-vs-read decision agree on one
mandatory correction: a `hy-memory` Matter that carries memory refs must not
be served as ready when `MatterStore` has no lifecycle source. Today
`_load()` gates the lifecycle block on `self._lifecycle_source is not None`,
so an unwired store silently validates the ledger mirror only and can serve a
node HY has already set aside.

This test pins the fail-closed requirement. It is owned by C3 as a lifecycle
guard; the fix, if it moves, is in C4/C0-owned `matters/store.py`.
"""

from __future__ import annotations

from hashlib import sha256

from test_matter_hy_integration import Bridge, process_turn, setup

from one_memory.matters.models import Citation, Claim, MatterDraft, MemoryRef
from one_memory.matters.store import MatterStore


def test_a_hy_matter_without_a_lifecycle_source_fails_closed(tmp_path) -> None:
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
            store = MatterStore(processor.tasks.database_path)
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
            read = store.get(saved.matter_id)
            assert read.availability == "memory_changed", (
                "a HY-backed matter with refs must not be served ready when the "
                "lifecycle source is unwired; expected memory_changed, got "
                f"{read.availability!r}"
            )
            assert read.claims == []
        finally:
            await processor.shutdown()

    import asyncio

    asyncio.run(scenario())
