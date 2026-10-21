#!/usr/bin/env python3
"""Measure the governed-memory content-index candidate path in isolation.

This is the C3 half of C4's governed-memory scale red. It creates the
production governance/evidence shape, then calls the maintained candidate
predicate through `MemoryGovernanceStore.find_confirmed_matching_terms`.
It does not claim the context read path is fixed until C4 wires the same
predicate into `context_memory.py`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from one_memory.imports.grants import GRANT_SCHEMA  # noqa: E402
from one_memory.imports.storage import SCHEMA as EVIDENCE_SCHEMA  # noqa: E402
from one_memory.memory_governance import (  # noqa: E402
    GOVERNANCE_SCHEMA,
    MemoryGovernanceStore,
)

ROWS = 430_000
TARGET = "独特记忆目标短语"
NOW = "2026-09-01T00:00:00+00:00"


def _fill(db: sqlite3.Connection) -> None:
    evidence_sql = """INSERT INTO evidence (
        evidence_id,idempotency_key,user_id,source_id,conversation_id,message_id,
        source_ordinal,content_kind,role,written_by,created_at,verbatim,content_hash,
        revision,imported_at,updated_at,ingest_seq
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    memory_sql = """INSERT INTO governed_memories (
        memory_id,user_id,kind,status,content,scopes_json,revision,created_at,updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?)"""
    link_sql = "INSERT INTO governed_memory_evidence(memory_id,evidence_id) VALUES (?,?)"
    for left in range(0, ROWS, 10_000):
        right = min(ROWS, left + 10_000)
        evidence_rows = []
        memory_rows = []
        links = []
        for index in range(left, right):
            evidence_id = f"e-{index:07d}"
            content = (
                f"这是 {TARGET}，用于验证治理记忆词法命中。"
                if index == 0
                else f"普通历史记录 {index} 不包含查询目标"
            )
            evidence_rows.append(
                (
                    evidence_id,
                    evidence_id,
                    "local",
                    "workbuddy",
                    "conversation",
                    evidence_id,
                    index,
                    "chat",
                    "user",
                    "person",
                    NOW,
                    content,
                    f"hash-{index}",
                    1,
                    NOW,
                    NOW,
                    index + 1,
                )
            )
            memory_id = f"m-{index:07d}"
            memory_rows.append(
                (
                    memory_id,
                    "local",
                    "working",
                    "confirmed",
                    content,
                    '["all-apps"]',
                    1,
                    NOW,
                    NOW,
                )
            )
            links.append((memory_id, evidence_id))
        db.executemany(evidence_sql, evidence_rows)
        db.executemany(memory_sql, memory_rows)
        db.executemany(link_sql, links)
        db.commit()


def _run(repeat: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="c3-content-scale-") as raw:
        path = Path(raw) / "one-memory.sqlite3"
        db = sqlite3.connect(path)
        db.executescript(EVIDENCE_SCHEMA + GOVERNANCE_SCHEMA + GRANT_SCHEMA)
        started = time.perf_counter()
        _fill(db)
        insert_ms = (time.perf_counter() - started) * 1000
        db.close()

        store = MemoryGovernanceStore(path)
        terms = ("独特", "特记", "记忆", "忆目", "目标", "标短", "短语")
        first_started = time.perf_counter()
        first, first_more = store.find_confirmed_matching_terms(
            user_id="local", terms=terms, scopes=("all-apps",)
        )
        assert "m-0000000" in {memory.memory_id for memory in first}
        first_ms = (time.perf_counter() - first_started) * 1000
        samples = []
        for _ in range(repeat):
            started = time.perf_counter()
            found, more = store.find_confirmed_matching_terms(
                user_id="local", terms=terms, scopes=("all-apps",)
            )
            samples.append((time.perf_counter() - started) * 1000)
            assert "m-0000000" in {memory.memory_id for memory in found}
        with sqlite3.connect(path) as connection:
            plan = [
                str(row[3])
                for row in connection.execute(
                    """EXPLAIN QUERY PLAN SELECT m.memory_id FROM governed_memories m
                    WHERE m.user_id='local' AND m.status='confirmed'
                    AND m.memory_id IN (
                      SELECT memory_id FROM governed_memories_terms WHERE term=?)
                    ORDER BY m.updated_at DESC,m.memory_id LIMIT 9""",
                    ("特记",),
                )
            ]
        ordered = sorted(samples)
        return {
            "rows": ROWS,
            "query": TARGET,
            "repeat": repeat,
            "first_ms": round(first_ms, 3),
            "p50_ms": round(statistics.median(samples), 3),
            "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
            "samples_ms": [round(value, 3) for value in samples],
            "insert_ms": round(insert_ms, 3),
            "database_bytes": path.stat().st_size,
            "first_matches": [memory.memory_id for memory in first],
            "first_more": first_more,
            "last_more": more,
            "plan": plan,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 5 <= args.repeat <= 100:
        raise SystemExit("repeat must be 5..100")
    report = _run(args.repeat)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["p95_ms"] < 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
