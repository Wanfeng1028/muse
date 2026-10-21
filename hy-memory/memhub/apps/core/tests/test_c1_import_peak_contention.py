"""Import-peak lock contention is truthful and replayable.

O-17 is not "must never see a lock"; the real product can see one under
contention. What C1 owns is the behavior at that moment:

- the failed commit must not advance Evidence or a cursor;
- the job must reach FAILED and count a machine-coded `database_locked`;
- once the lock clears, a rerun must import every record exactly once.
"""

import asyncio
import sqlite3
from collections import Counter

import pytest

from one_memory.imports import runner as runner_module
from one_memory.imports.adapters import ScannedEvidence
from one_memory.imports.jobs import ImportStatus
from one_memory.imports.storage import EvidenceStore
from tests.test_import_runner import FixtureAdapter, cursor, evidence, stores

pytestmark = pytest.mark.contract


def test_locked_import_commit_is_failed_and_replayable(tmp_path, monkeypatch):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    original_put = EvidenceStore.put
    original_record = runner_module.record_database_error
    database_errors: Counter[tuple[str, str]] = Counter()
    armed = {"value": True}

    def fail_once(self, item, **kwargs):
        if armed["value"]:
            armed["value"] = False
            raise sqlite3.OperationalError("database is locked")
        return original_put(self, item, **kwargs)

    def record(component: str, error: BaseException) -> str:
        code = original_record(component, error)
        database_errors[(component, code)] += 1
        return code

    monkeypatch.setattr(EvidenceStore, "put", fail_once)
    monkeypatch.setattr(runner_module, "record_database_error", record)

    events = [
        ScannedEvidence(evidence=evidence(str(index)), cursor=cursor(f"line:{index}"))
        for index in range(8)
    ]
    try:
        failed = asyncio.run(
            runner_module.ImportRunner(evidence_store=records, job_store=jobs).run(
                adapter=FixtureAdapter(events),
                job_id=job.job_id,
            )
        )
    except sqlite3.OperationalError as error:
        assert "locked" in str(error)
        failed = jobs.require(job.job_id)

    assert failed.status is ImportStatus.FAILED
    assert failed.stored == failed.errors == records.count() == 0
    assert jobs.get_source_cursors(user_id="local", source_id="fixture") == {}
    assert database_errors[("import.runner", "database_locked")] == 1

    monkeypatch.undo()
    recovered = asyncio.run(
        runner_module.ImportRunner(evidence_store=records, job_store=jobs).run(
            adapter=FixtureAdapter(events),
            job_id=job.job_id,
        )
    )
    assert recovered.status is ImportStatus.COMPLETED
    assert recovered.stored == 8
    assert records.count() == 8
