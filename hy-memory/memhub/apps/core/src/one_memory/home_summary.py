"""Bounded homepage projection without loading every memory into the renderer."""

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from one_memory.database_access import main_database
from one_memory.memory_evidence_freshness import register_memory_freshness


class HomeLatestMemory(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: str
    content: str
    truncated: bool
    revision: int
    action: str
    updated_at: datetime
    source_ids: tuple[str, ...]


class HomeSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_count: int
    latest: HomeLatestMemory | None
    observed_at: datetime
    #: 2026-10-12: the read hit its deadline and the numbers below are not a
    #: snapshot of reality. Callers should keep their previous summary on
    #: screen instead of treating count=0 as "no memories".
    stale: bool = False


class HomeSummaryUnavailable(Exception):
    """The homepage projection could not be read inside its own deadline.

    Raised instead of letting SQLite's interrupt escape as a bare
    `OperationalError`, so the route can answer with an empty projection
    rather than a 500.
    """


def read_home_summary(database_path: Path, *, user_id: str = "local") -> HomeSummary:
    # The exclusion mirrors SourceReadAccess: one revoked active citation hides
    # the whole memory. Permission filtering precedes both count and LIMIT.
    # `+link.active` keeps SQLite on the (memory_id, evidence_id) primary key.
    # Without the unary plus it picks the (active, ...) index and walks every
    # active link once per memory: 2.9 s instead of 0.07 s on a 1,810-memory
    # library, enough to time the homepage out whenever the machine is busy.
    readable = """
        m.user_id = ? AND m.status = 'confirmed' AND m.deleted_at IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM governed_memory_evidence link
            JOIN evidence e ON e.evidence_id = link.evidence_id
            JOIN source_grants g ON g.user_id=e.user_id AND g.source_id=e.source_id
            WHERE link.memory_id=m.memory_id AND +link.active=1
              AND g.revoked_at IS NOT NULL
        )
        AND NOT EXISTS (
            SELECT 1 FROM governed_memory_evidence link
            LEFT JOIN evidence e ON e.evidence_id = link.evidence_id
            WHERE link.memory_id=m.memory_id AND +link.active=1
              AND (e.evidence_id IS NULL OR e.user_id != m.user_id)
        )
    """
    # The total counts with the cheap permission filters only: the per-row
    # freshness UDF scales with the whole library and can burn the whole read
    # budget on its own (D22). Product accepted a small drift here; the rows
    # that are actually displayed are still checked row by row below.
    with main_database(database_path).read() as db:
        deadline = time.monotonic() + 5
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN")
            count = db.execute(
                f"SELECT COUNT(*) FROM governed_memories m WHERE {readable}", (user_id,)
            ).fetchone()[0]
            readable += " AND " + register_memory_freshness(db)
            row = db.execute(
                f"""SELECT m.memory_id, substr(m.content,1,320) AS content,
                    length(m.content)>320 AS truncated, m.revision,
                    COALESCE(v.action, 'unknown') AS action, m.updated_at
                    FROM governed_memories m
                    LEFT JOIN governed_memory_versions v
                      ON v.memory_id=m.memory_id AND v.revision=m.revision
                    WHERE {readable}
                    ORDER BY m.updated_at DESC, m.memory_id LIMIT 1""",
                (user_id,),
            ).fetchone()
            latest = None
            if row is not None:
                sources = db.execute(
                    """SELECT DISTINCT e.source_id FROM governed_memory_evidence link
                    JOIN evidence e ON e.evidence_id=link.evidence_id
                    WHERE link.memory_id=? AND +link.active=1 ORDER BY e.source_id""",
                    (row["memory_id"],),
                ).fetchall()
                latest = HomeLatestMemory(
                    memory_id=row["memory_id"],
                    content=row["content"],
                    truncated=bool(row["truncated"]),
                    revision=row["revision"],
                    action=row["action"],
                    updated_at=row["updated_at"],
                    source_ids=tuple(source[0] for source in sources),
                )
        except sqlite3.Error as error:
            # The progress handler above is what interrupts this read, so a
            # slow homepage surfaces as SQLITE_INTERRUPT (code 9) and used to
            # escape as a 500. 2026-10-12: answer with a `stale` projection
            # instead of raising: the caller keeps its last good summary on
            # screen (the UI poll retries within 10s), and the homepage never
            # zeroes out or errors just because the machine is busy importing.
            if getattr(error, "sqlite_errorcode", None) != sqlite3.SQLITE_INTERRUPT:
                raise
            return HomeSummary(
                memory_count=0,
                latest=None,
                observed_at=datetime.now(UTC),
                stale=True,
            )
        return HomeSummary(memory_count=count, latest=latest, observed_at=datetime.now(UTC))
