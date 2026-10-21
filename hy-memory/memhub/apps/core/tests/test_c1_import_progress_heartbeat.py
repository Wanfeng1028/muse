"""Read progress heartbeats: visible at least once a second, never splitting a batch.

A long single file used to emit no progress between files, so the job's visible
counts could stand still for seconds. The heartbeat fixes that, but it must not
change what one write transaction commits, because a failed commit has to roll
back exactly one batch.
"""

import asyncio

from one_memory.imports import runner as runner_module
from one_memory.imports.adapters import ScanPhase, ScanProgressEvent
from one_memory.imports.sources import common as source_common
from tests.test_c1_import_event_matrix import MatrixSource


def test_heartbeat_boundary_matches_the_runner_batch_size():
    assert source_common._HEARTBEAT_BATCH_BOUNDARY == runner_module.EVIDENCE_BATCH_RECORDS, (
        "a read heartbeat must land on a write-batch boundary, not inside one"
    )


def test_sqlite_evidence_writes_use_short_batches():
    assert runner_module.EVIDENCE_BATCH_RECORDS <= 10, (
        "real duplicate-heavy imports held SQLite's sole writer for over five seconds at 50 rows"
    )


def test_a_long_file_emits_progress_while_it_is_being_read(tmp_path):
    fixture = MatrixSource(tmp_path, "codex")
    fixture.write("session", [f"message {index}" for index in range(600)])

    async def scenario():
        adapter = fixture.registration.create_adapter(fixture.authorized_root())
        phases = []
        from one_memory.imports.adapters import ScanOptions

        async for event in adapter.scan(ScanOptions(cursors={})):
            if isinstance(event, ScanProgressEvent):
                phases.append(event.phase)
        return phases

    phases = asyncio.run(scenario())
    assert ScanPhase.EMIT in phases, "reading a long file must report progress, not just file ends"
    assert phases[0] is ScanPhase.DISCOVER
    assert phases[-1] is ScanPhase.DONE


def test_heartbeats_do_not_split_the_first_write_batch(tmp_path, monkeypatch):
    """What a failed commit rolls back must stay exactly one batch."""
    fixture = MatrixSource(tmp_path, "codex")
    total = runner_module.EVIDENCE_BATCH_RECORDS + 10
    fixture.write("session", [f"line {index}" for index in range(total)])

    batches = []
    original = runner_module.ImportRunner._record_batch

    def observed(self, batch, **kwargs):
        batches.append(len(batch))
        return original(self, batch, **kwargs)

    monkeypatch.setattr(runner_module.ImportRunner, "_record_batch", observed)
    assert fixture.run().stored == total
    assert batches, "the import must actually record batches"
    assert max(batches) <= runner_module.EVIDENCE_BATCH_RECORDS
