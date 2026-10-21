"""D93 test 1: the written-ahead visibility must agree with the exact check.

Plan `读写隔离方案-20261009.html` section 8, row 1. Random sequences of
revoking and restoring a source, changing a citation, issuing a new proof,
correcting and deleting a memory. After every step the set of memories the
library shows is computed twice:

* `exact_visible_ids`: the expected function. It is today's read path, paged
  through `read_memory_library(active_only=True)` with no limit, so it carries
  every rule the UI applies now (status, deletion, revoked citation, foreign
  citation, freshness UDF). A second, independent route through
  `SourceReadAccess.filter` must agree with it; if those two ever differ the
  exact check itself is inconsistent and A has nothing stable to match.
* `materialized_visible_ids`: what A's read condition returns, written from
  the data contract in plan section 6 rather than from A's code:
  `visible=1 AND NOT dirty`, plus the dirty rows and the rows with no
  conclusion yet sent through the exact check.
* The product reads themselves with A's switch on
  (`ONE_MEMORY_READ_VISIBILITY=derived`): the library and the per-item filter.

When A is in the build, the fixture installs A's tables and triggers the way
Core does at start (`memory_visibility.startup`), and `_drain_visibility` runs
A's own background batch (`api._visibility_batch`) until idle, so every step is
compared both before the background recompute and after it. Dropping any one
trigger turns this red (checked by removing the evidence-update trigger: 4 of
40 sequences fail). Without A the materialized half is skipped with a reason.

`ONE_MEMORY_D93_SEQUENCES` sets the number of sequences: the gate is 1000, the
default here keeps the file inside a normal test run.
"""

from __future__ import annotations

import os
import random
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from one_memory.database_access import main_database
from one_memory.imports.grants import GRANT_SCHEMA
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_evidence_freshness import register_memory_freshness
from one_memory.memory_governance import (
    MemoryDraft,
    MemoryGovernanceStore,
    MemoryKind,
    MemoryStatus,
)
from one_memory.memory_library import read_memory_library
from one_memory.memory_tasks import MemoryTaskOutput, MemoryTaskStore, evidence_ref
from one_memory.source_read_access import SourceReadAccess
from tests.person_door import as_person

SEQUENCES = int(os.environ.get("ONE_MEMORY_D93_SEQUENCES", "40"))
STEPS = int(os.environ.get("ONE_MEMORY_D93_STEPS", "12"))
SOURCES = ("cursor", "codex", "workbuddy")
USER = "local"


# --- expected function: today's exact check ---------------------------------


def exact_visible_ids(database: Path, user_id: str = USER) -> set[str]:
    """Every memory the library would show now, by today's exact read path."""
    seen: set[str] = set()
    offset = 0
    while True:
        page = read_memory_library(
            database, user_id=user_id, active_only=True, offset=offset, limit=100
        )
        ids = [item.memory_id for item in page.items]
        seen.update(ids)
        if len(ids) < 100:
            return seen
        offset += 100


def exact_visible_ids_by_filter(database: Path, user_id: str = USER) -> set[str]:
    """Same answer through the per-item route the map and recall use."""
    governance = MemoryGovernanceStore(database)
    confirmed = [
        item
        for item in governance.list(
            user_id=user_id, status=MemoryStatus.CONFIRMED, limit=500, lifecycle=None
        )
        if item.deleted_at is None
    ]
    return {item.memory_id for item in SourceReadAccess(database).filter(confirmed)}


# --- A's side, from the data contract ----------------------------------------


def _has_table(db: sqlite3.Connection, name: str) -> bool:
    return (
        db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        is not None
    )


def _a_present() -> bool:
    try:
        from one_memory import memory_visibility  # noqa: F401
    except ImportError:
        return False
    return True


def _install_a(database: Path) -> None:
    """What Core does at start: derived tables and triggers, no version change."""
    from one_memory import memory_visibility

    memory_visibility.startup(database)
    with main_database(database).read() as db:
        names = {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
    expected = {
        statement.split("EXISTS", 1)[1].split()[0]
        for _table, statement in memory_visibility._trigger_sql()
    }
    # A trigger skipped because its table did not exist yet would make every
    # later comparison pass for the wrong reason.
    assert expected <= names, f"triggers missing: {sorted(expected - names)}"


def _drain_visibility(database: Path) -> None:
    """Run A's own background batch (`api._visibility_batch`) until idle."""
    from one_memory.api import _visibility_batch

    for _ in range(1_000):
        if _visibility_batch(database) == 0:
            return
    raise AssertionError("visibility recompute did not go idle")


def materialized_visible_ids(database: Path, user_id: str = USER) -> set[str] | None:
    """A's read contract (plan section 6). None while A is not in the build.

    A stored conclusion is used only when it is not marked dirty; a memory
    with no conclusion yet, or a dirty one, is checked exactly. So any
    disagreement with the exact check here means a trigger missed a change.
    """
    with main_database(database).read() as db:
        if not _has_table(db, "memory_visibility"):
            return None
        db.execute("BEGIN")
        owned = {
            row[0]
            for row in db.execute(
                "SELECT memory_id FROM governed_memories WHERE user_id=?", (user_id,)
            )
        }
        stored = {
            row[0]: int(row[1])
            for row in db.execute(
                "SELECT memory_id, visible FROM memory_visibility "
                "WHERE memory_id NOT IN (SELECT memory_id FROM memory_visibility_dirty)"
            )
        }
        db.execute("COMMIT")
    exact = exact_visible_ids(database, user_id)
    trusted = {memory_id for memory_id, visible in stored.items() if visible} & owned
    unanswered = owned - set(stored)
    return trusted | (unanswered & exact)


# --- fixture and mutations ----------------------------------------------------


class World:
    def __init__(self, root: Path, rng: random.Random) -> None:
        self.database = root / "one-memory.sqlite3"
        self.rng = rng
        with sqlite3.connect(self.database) as setup:
            setup.executescript(GRANT_SCHEMA)
            now = datetime.now(UTC).isoformat()
            for source in SOURCES:
                setup.execute(
                    "INSERT INTO source_grants VALUES (?,?,?,?,?,NULL)",
                    (USER, source, f"/fixture/{source}", "default", now),
                )
        self.evidence = EvidenceStore(self.database)
        self.tasks = MemoryTaskStore(self.database)
        self.governance = MemoryGovernanceStore(self.database)
        self.person = as_person(self.governance)
        self.records = []
        for index in range(9):
            self.records.append(
                self.evidence.put(
                    EvidenceInput(
                        source_id=SOURCES[index % len(SOURCES)],
                        conversation_id=f"conversation-{index}",
                        message_id=f"m-{index}",
                        correlation_id=f"m-{index}",
                        role="user",
                        written_by=WrittenBy.PERSON,
                        verbatim=f"第 {index} 条对话原文。",
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
            )
        self.memories: dict[str, int] = {}
        self.citations: dict[str, tuple] = {}
        self.proofs = 0
        for index in range(8):
            cited = tuple(rng.sample(self.records, rng.choice((1, 1, 2))))
            memory = self.person.create(
                MemoryDraft(
                    user_id=USER,
                    kind=MemoryKind.CHAT,
                    content=f"记忆 {index}",
                    scopes=("all-apps",),
                    evidence_ids=tuple(record.evidence_id for record in cited),
                ),
                request_id=f"create-{index}",
            )
            self.memories[memory.memory_id] = memory.revision
            self.citations[memory.memory_id] = cited
            if rng.random() < 0.8:
                self.prove(memory.memory_id)
        if _a_present():
            _install_a(self.database)

    def prove(self, memory_id: str) -> None:
        self.proofs += 1
        self.tasks.save_output(
            MemoryTaskOutput(
                task_id=f"task-{self.proofs}",
                memory_id=memory_id,
                memory_revision=self.memories[memory_id],
                hy_memory_id=f"hy-{self.proofs}",
                owner="user",
                layer="L2_FACT",
                engine_version="fixture",
                support_refs=tuple(evidence_ref(record) for record in self.citations[memory_id]),
            )
        )

    def _sql(self, statement: str, values: tuple) -> None:
        with sqlite3.connect(self.database) as db:
            db.execute(statement, values)

    def step(self) -> str:
        live = [key for key, revision in self.memories.items() if revision > 0]
        action = self.rng.choice(
            ("revoke", "restore", "restore", "edit_evidence", "prove", "correct", "delete")
        )
        if action == "revoke":
            self._sql(
                "UPDATE source_grants SET revoked_at=? WHERE user_id=? AND source_id=?",
                (datetime.now(UTC).isoformat(), USER, self.rng.choice(SOURCES)),
            )
        elif action == "restore":
            self._sql(
                "UPDATE source_grants SET revoked_at=NULL WHERE user_id=? AND source_id=?",
                (USER, self.rng.choice(SOURCES)),
            )
        elif action == "edit_evidence":
            # A new revision of one cited message: proofs that named the old
            # revision stop matching, exactly what re-import of an edited
            # conversation does.
            record = self.rng.choice(self.records)
            self._sql(
                "UPDATE evidence SET revision=revision+1 WHERE evidence_id=?",
                (record.evidence_id,),
            )
            self.records = [self.evidence.get(item.evidence_id) or item for item in self.records]
            for memory_id, cited in self.citations.items():
                self.citations[memory_id] = tuple(
                    next(r for r in self.records if r.evidence_id == c.evidence_id) for c in cited
                )
        elif action == "prove" and live:
            self.prove(self.rng.choice(live))
        elif action == "correct" and live:
            memory_id = self.rng.choice(live)
            memory = self.person.correct(
                memory_id,
                user_id=USER,
                request_id=f"correct-{self.rng.random()}",
                expected_revision=self.memories[memory_id],
                content=f"改过的记忆 {self.rng.random():.6f}",
            )
            self.memories[memory_id] = memory.revision
        elif action == "delete" and live:
            memory_id = self.rng.choice(live)
            self.person.delete(
                memory_id,
                user_id=USER,
                request_id=f"delete-{self.rng.random()}",
                expected_revision=self.memories[memory_id],
            )
            self.memories[memory_id] = 0
        return action


def _product_reads(database: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[set, set]:
    """The library and the per-item filter with A's switch on (`derived`)."""
    monkeypatch.setenv("ONE_MEMORY_READ_VISIBILITY", "derived")
    try:
        return exact_visible_ids(database), exact_visible_ids_by_filter(database)
    finally:
        monkeypatch.setenv("ONE_MEMORY_READ_VISIBILITY", "exact")


def _compare(world: World, where: str, monkeypatch: pytest.MonkeyPatch) -> None:
    exact = exact_visible_ids(world.database)
    by_filter = exact_visible_ids_by_filter(world.database)
    assert by_filter == exact, f"{where}: two exact routes disagree"
    materialized = materialized_visible_ids(world.database)
    if materialized is not None:
        assert materialized == exact, f"{where}: before recompute"
        library, filtered = _product_reads(world.database, monkeypatch)
        assert library == exact, f"{where}: library with the switch on, before recompute"
        assert filtered == exact, f"{where}: filter with the switch on, before recompute"
        _drain_visibility(world.database)
        assert materialized_visible_ids(world.database) == exact, f"{where}: after recompute"
        library, filtered = _product_reads(world.database, monkeypatch)
        assert library == exact, f"{where}: library with the switch on, after recompute"
        assert filtered == exact, f"{where}: filter with the switch on, after recompute"


@pytest.mark.parametrize("seed", range(SEQUENCES))
def test_visibility_matches_the_exact_check_after_every_step(tmp_path, seed, monkeypatch):
    # The expected function must be today's exact path whatever the
    # environment says, or it would be comparing the cache with itself.
    monkeypatch.setenv("ONE_MEMORY_READ_VISIBILITY", "exact")
    rng = random.Random(seed)
    world = World(tmp_path, rng)
    _compare(world, f"seed {seed} start", monkeypatch)
    for index in range(STEPS):
        action = world.step()
        _compare(world, f"seed {seed} step {index} {action}", monkeypatch)


def test_a_is_in_the_build_or_this_file_says_so(tmp_path):
    world = World(tmp_path, random.Random(0))
    if materialized_visible_ids(world.database) is None:
        pytest.skip("memory_visibility absent: A not merged, materialized half not exercised")


def test_the_expected_function_sees_a_revoked_source(tmp_path):
    """The oracle itself must move; otherwise every comparison is vacuous."""
    world = World(tmp_path, random.Random(1))
    before = exact_visible_ids(world.database)
    assert before, "fixture produced no visible memory"
    with sqlite3.connect(world.database) as db:
        db.execute("UPDATE source_grants SET revoked_at='2026-10-09T00:00:00+00:00'")
    assert exact_visible_ids(world.database) == set()
    with sqlite3.connect(world.database) as db:
        db.execute("UPDATE source_grants SET revoked_at=NULL")
    assert exact_visible_ids(world.database) == before


def test_the_expected_function_sees_a_stale_citation(tmp_path):
    world = World(tmp_path, random.Random(2))
    with main_database(world.database).read() as db:
        db.execute("BEGIN")
        register_memory_freshness(db)
        proven = [
            row[0] for row in db.execute("SELECT DISTINCT memory_id FROM memory_task_outputs")
        ]
        db.execute("COMMIT")
    target = next(m for m in proven if m in exact_visible_ids(world.database))
    record = world.citations[target][0]
    with sqlite3.connect(world.database) as db:
        db.execute(
            "UPDATE evidence SET revision=revision+1 WHERE evidence_id=?", (record.evidence_id,)
        )
    assert target not in exact_visible_ids(world.database)


def test_the_random_steps_actually_move_the_visible_set(tmp_path):
    """Guard against a vacuous comparison: each kind of step must change what shows."""
    moved: dict[str, int] = {}
    for seed in range(20):
        root = tmp_path / str(seed)
        root.mkdir()
        world = World(root, random.Random(10_000 + seed))
        before = exact_visible_ids(world.database)
        for _ in range(STEPS):
            action = world.step()
            after = exact_visible_ids(world.database)
            if after != before:
                moved[action] = moved.get(action, 0) + 1
            before = after
    for action in ("revoke", "restore", "edit_evidence", "delete"):
        assert moved.get(action, 0) > 0, f"{action} never changed the visible set: {moved}"
