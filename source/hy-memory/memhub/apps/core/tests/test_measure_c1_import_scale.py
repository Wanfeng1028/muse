"""The import measurement must not report fabricated or conflated counters.

`measure_c1_import_scale.py` is cited as performance evidence. Its
`hashes` field previously stayed at zero because nothing counted hashing, and
its `duplicates` field was just the job's `merged` count. Those are different
facts: a merge is a normal update, while a duplicate is an extra Evidence row
for one idempotency key.
"""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from tests.measure_c1_import_scale import Counter, _duplicate_evidence_rows, measure

pytestmark = pytest.mark.contract


def test_scale_measurement_counts_hashes_and_duplicates_independently(tmp_path: Path) -> None:
    result = asyncio.run(measure(tmp_path, target=200, conversations=2))

    assert result["stored"] == 200
    assert result["hashes"] >= 200, result
    assert result["duplicates"] == 0
    assert result["opens"] > 0
    assert result["bytes_read"] > 0
    assert result["writer_waits"] >= 0
    assert result["writer_wait_ms_total"] >= 0
    assert result["writer_wait_ms_process_max"] >= 0


def test_scale_counter_uninstalls_cleanly(tmp_path: Path) -> None:
    counter = Counter()
    counter.install()
    counter.uninstall()
    counter.uninstall()

    result = asyncio.run(measure(tmp_path, target=40, conversations=1))
    assert result["stored"] == 40
    assert result["hashes"] >= 40


def test_duplicate_counter_reports_extra_rows_not_merges(tmp_path: Path) -> None:
    database = tmp_path / "duplicates.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY, idempotency_key TEXT)"
        )
        connection.executemany(
            "INSERT INTO evidence VALUES (?, ?)",
            [
                ("e-1", "same"),
                ("e-2", "same"),
                ("e-3", "same"),
                ("e-4", "other"),
            ],
        )

    assert _duplicate_evidence_rows(database) == 2
