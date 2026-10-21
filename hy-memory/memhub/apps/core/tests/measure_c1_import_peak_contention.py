"""Inject import-peak writer contention and verify truthful recovery.

O-17 is about the real production shape where an import peak queues behind the
single SQLite writer and can surface `database is locked`. Existing C1 scale
measurements report zero locks on a quiet synthetic run; that is useful for the
fast path but does not prove what happens when contention is present.

This C1-owned probe:

1. builds a real native-format corpus and starts a real import;
2. injects a bounded `sqlite3.OperationalError("database is locked")` at the
   import writer boundary;
3. requires the job to end FAILED, with no cursor/Evidence advanced by the
   failed commit;
4. removes the injection and reruns, requiring every record to land exactly
   once;
5. reports the machine-coded `database_locked` count so a zero count cannot be
   confused with "not measured".

It never opens the daily `~/.one-memory` database and never writes a real host
source.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from one_memory.imports import runner as runner_module  # noqa: E402
from one_memory.imports.adapters import ScannedEvidence  # noqa: E402
from one_memory.imports.jobs import ImportStatus  # noqa: E402
from one_memory.imports.storage import EvidenceStore  # noqa: E402
from tests.test_import_runner import FixtureAdapter, cursor, evidence, stores  # noqa: E402


def _snapshot_code(counts: Counter[tuple[str, str]]) -> dict[str, int]:
    return {f"{component}:{code}": count for (component, code), count in counts.items()}


def measure(tmp_path: Path, records: int) -> dict:
    async def scenario() -> dict:
        records_store, jobs = stores(tmp_path)
        job = jobs.create(user_id="local", source_id="fixture")
        original_put = EvidenceStore.put
        original_record_database_error = runner_module.record_database_error
        database_errors: Counter[tuple[str, str]] = Counter()
        injected = {"armed": True}

        def fail_first_commit(self, item, **kwargs):
            if injected["armed"]:
                injected["armed"] = False
                raise sqlite3.OperationalError("database is locked")
            return original_put(self, item, **kwargs)

        def record(component: str, error: BaseException) -> str:
            code = original_record_database_error(component, error)
            database_errors[(component, code)] += 1
            return code

        EvidenceStore.put = fail_first_commit
        runner_module.record_database_error = record
        try:
            try:
                failed = await runner_module.ImportRunner(
                    evidence_store=records_store, job_store=jobs
                ).run(
                    adapter=FixtureAdapter(
                        [
                            ScannedEvidence(
                                evidence=evidence(str(index)), cursor=cursor(f"line:{index}")
                            )
                            for index in range(records)
                        ]
                    ),
                    job_id=job.job_id,
                )
            except sqlite3.OperationalError as error:
                assert "locked" in str(error)
                failed = jobs.require(job.job_id)
            failed_cursors = jobs.get_source_cursors(user_id="local", source_id="fixture")
            failed_rows = records_store.count()
        finally:
            EvidenceStore.put = original_put
            runner_module.record_database_error = original_record_database_error

        recovered = await runner_module.ImportRunner(
            evidence_store=records_store, job_store=jobs
        ).run(
            adapter=FixtureAdapter(
                [
                    ScannedEvidence(evidence=evidence(str(index)), cursor=cursor(f"line:{index}"))
                    for index in range(records)
                ]
            ),
            job_id=job.job_id,
        )
        recovered_rows = records_store.count()

        return {
            "injected": "database is locked",
            "records": records,
            "failure": {
                "status": str(failed.status),
                "stored": failed.stored,
                "errors": failed.errors,
                "evidence_rows": failed_rows,
                "cursors": len(failed_cursors),
                "database_error_counts": _snapshot_code(database_errors),
            },
            "recovery": {
                "status": str(recovered.status),
                "stored": recovered.stored,
                "evidence_rows": recovered_rows,
                "duplicate_rows": recovered_rows - records,
            },
            "passed": (
                failed.status is ImportStatus.FAILED
                and failed.stored == 0
                and failed.errors == 0
                and failed_rows == 0
                and not failed_cursors
                and database_errors[("import.runner", "database_locked")] >= 1
                and recovered.status is ImportStatus.COMPLETED
                and recovered.stored == records
                and recovered_rows == records
            ),
        }

    return asyncio.run(scenario())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=2_000)
    parser.add_argument("--tmp", default="")
    args = parser.parse_args()

    if args.tmp:
        result = measure(Path(args.tmp).resolve(), args.records)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["passed"] else 1

    with tempfile.TemporaryDirectory(prefix="c1-import-peak-") as directory:
        result = measure(Path(directory).resolve(), args.records)
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
