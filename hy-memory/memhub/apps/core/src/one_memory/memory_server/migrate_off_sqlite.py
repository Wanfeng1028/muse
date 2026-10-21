"""A1-06: the one-time SQLite -> MySQL migration, and its reconciliation.

**Not used under D56.** D56 makes SQLite the sole business store (overriding
D53's MySQL-only decision), so this migration must never run; `store_binding`
never resolves to MySQL and the D56 cleanup (`d56-mysql-legacy-cleanup.md`)
lists this module for deletion once the Captain authorizes it. Kept here only
so the removal is a reviewed decision rather than a silent drop, and so the
reconciliation design (counts + hashes per table) is preserved as reference.

A migration that only copies rows is indistinguishable from one that lost
rows. So this module treats **reconciliation as the deliverable**: counts and
hashes must agree per table before the migration may be called done, and any
disagreement is reported per table rather than as a single pass/fail.

The plan is explicit and ordered, because each step has a different failure
cost:

1. preflight  — refuse early on anything that would make the copy unsafe
2. snapshot   — a read-only copy, so the user's live database is never the
                thing being read mid-write
3. copy       — per table, resumable
4. reconcile  — counts and content hashes per table
5. cutover    — only after reconciliation agrees

Resume matters: a 2.3 GB database interrupted at 90% should continue from the
last committed table, not restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Tables in copy order. Dependencies first: a child row cannot be verified
#: against a parent that has not been copied yet.
TABLE_ORDER: tuple[str, ...] = (
    "evidence",
    "evidence_origins",
    "evidence_versions",
    "source_cursors",
    "import_jobs",
    "memory_tasks",
    "governed_memories",
    "governed_memory_versions",
    "governed_memory_evidence",
)


@dataclass(frozen=True)
class Preflight:
    sqlite_bytes: int
    free_bytes: int
    #: Target MySQL must be empty; copying into a populated schema would merge
    #: two datasets and make the reconciliation meaningless.
    target_empty: bool
    target_schema_version: int


def preflight_verdict(state: Preflight) -> tuple[bool, str]:
    """Whether the migration may begin, and the reason if not."""
    if not state.target_empty:
        return False, "target MySQL is not empty; refusing to merge two datasets"
    if state.target_schema_version != 0:
        return False, "target already migrated; a second run would duplicate data"
    # Headroom for the copy plus a working margin, not just the file size.
    if state.free_bytes < state.sqlite_bytes * 2:
        return False, "not enough free space for a copy plus working margin"
    return True, ""


def migration_plan() -> tuple[str, ...]:
    """The ordered steps. Snapshot precedes copy; reconcile precedes cutover."""
    return ("preflight", "snapshot", "copy", "reconcile", "cutover")


@dataclass(frozen=True)
class TableCounts:
    table: str
    source_rows: int
    target_rows: int
    #: Hash of the ordered row identities, so a same-count different-content
    #: mismatch is caught rather than assumed fine.
    source_digest: str = ""
    target_digest: str = ""


@dataclass(frozen=True)
class TableVerdict:
    table: str
    ok: bool
    reason: str = ""


def reconcile(counts: list[TableCounts]) -> tuple[list[TableVerdict], bool]:
    """Compare per table. Returns (verdicts, all_agree).

    Both count and digest are checked: equal counts with different contents is
    exactly the case a count-only check would pass while data was lost.
    """
    verdicts: list[TableVerdict] = []
    for item in counts:
        if item.source_rows != item.target_rows:
            verdicts.append(
                TableVerdict(
                    item.table,
                    False,
                    f"row count differs: {item.source_rows} -> {item.target_rows}",
                )
            )
            continue
        if item.source_digest != item.target_digest:
            verdicts.append(
                TableVerdict(item.table, False, "content digest differs at equal row count")
            )
            continue
        verdicts.append(TableVerdict(item.table, True))
    return verdicts, all(v.ok for v in verdicts)


def may_cutover(counts: list[TableCounts]) -> bool:
    """Cutover is gated on reconciliation agreeing for every table."""
    _verdicts, agree = reconcile(counts)
    return agree


@dataclass
class MigrationProgress:
    """Resumable progress: which tables are done."""

    completed: set[str] = field(default_factory=set)

    def remaining(self) -> tuple[str, ...]:
        return tuple(t for t in TABLE_ORDER if t not in self.completed)

    def mark(self, table: str) -> None:
        self.completed.add(table)


def resume_from(progress: MigrationProgress) -> tuple[str, ...]:
    """Tables still to copy, in dependency order."""
    return progress.remaining()
