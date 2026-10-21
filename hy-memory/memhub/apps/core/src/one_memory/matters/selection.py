import re
import sqlite3
from pathlib import Path
from typing import Literal

from one_memory.database_access import main_database
from one_memory.input_sanitization import sanitize_model_input
from one_memory.matters.models import (
    DeferredConversation,
    EvidenceSample,
    SampleRecord,
    SourceCoverage,
)

_PROBE = re.compile(
    r"^(?:ONE_MEMORY_(?:PROBE|SMOKE)|\[one-memory-probe\]|This is an automated .* probe)", re.I
)


_ORDINAL = re.compile(r"(?:^|:line:|:rowid:|:byte:)(\d+)$")


def _ordered(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """Order a conversation's rows by import order.

    This used to fall back to SQLite's `rowid`. MySQL has no `rowid`, and
    neither `imported_at` nor `evidence_id` reproduces insertion order (tried;
    it broke nine ordering tests), so migration 34 adds an explicit
    `ingest_seq`. Rows without one yet — a database migrated but not backfilled
    — fall back to rowid so the order never becomes arbitrary.
    """

    def key(row: sqlite3.Row) -> tuple[int, int]:
        # sqlite3.Row has no .get, and ruff wants no `in row.keys()`, so the
        # column list is taken once and compared against that.
        seq = row["ingest_seq"] if "ingest_seq" in tuple(row.keys()) else None
        return (0, seq) if seq is not None else (1, row["rowid"])

    ordinals = [_ORDINAL.search(row["source_ordinal"] or "") for row in rows]
    if all(ordinals):
        return [
            row
            for _, row in sorted(
                zip((int(match[1]) for match in ordinals if match), rows, strict=True),
                key=lambda pair: (pair[0], key(pair[1])),
            )
        ]
    if all(row["created_at"] for row in rows):
        return sorted(rows, key=lambda row: (row["created_at"], key(row)))
    # A missing timestamp must not move a correction to the end of its dialogue.
    return sorted(rows, key=key)


def select_evidence(
    database: Path, *, per_source: int | None = None, max_chars: int | None = None
) -> EvidenceSample:
    """Select complete conversations; explicit limits defer, never punch holes."""
    with main_database(database).read() as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        coverage = [
            SourceCoverage(**dict(r))
            for r in db.execute("""
            SELECT e.source_id, COUNT(*) records, COUNT(DISTINCT conversation_id) conversations,
                   SUM(created_at IS NULL) unknown_time_records
            FROM evidence e JOIN source_grants g USING(user_id,source_id)
            WHERE e.user_id='local' AND g.revoked_at IS NULL AND content_kind='raw_conversation'
                AND role IN ('user','assistant')
            GROUP BY e.source_id ORDER BY e.source_id
        """)
        ]
        result = EvidenceSample(records=[], coverage=coverage)
        used = 0
        for source in coverage:
            candidates = db.execute(
                """
                SELECT conversation_id
                FROM evidence WHERE user_id='local' AND source_id=?
                    AND content_kind='raw_conversation' AND role IN ('user','assistant')
                GROUP BY conversation_id
                ORDER BY MIN(COALESCE(ingest_seq, rowid))
            """,
                (source.source_id,),
            ).fetchall()
            for index, candidate in enumerate(candidates):
                rows = _ordered(
                    db.execute(
                        """
                    SELECT rowid,* FROM evidence WHERE user_id='local'
                    AND source_id=? AND conversation_id=?
                    AND content_kind='raw_conversation' AND role IN ('user','assistant')
                """,
                        (source.source_id, candidate["conversation_id"]),
                    ).fetchall(),
                )
                eligible = []
                for row in rows:
                    if _PROBE.search(row["verbatim"].strip()):
                        result.excluded_probe_records += 1
                        continue
                    eligible.append(row)
                if not eligible:
                    continue
                characters = sum(len(row["verbatim"]) for row in eligible)
                reason: Literal["conversation_limit", "character_budget"] | None = None
                if per_source is not None and index >= per_source:
                    reason = "conversation_limit"
                elif max_chars is not None and used + characters > max_chars:
                    reason = "character_budget"
                if reason:
                    result.deferred_conversations.append(
                        DeferredConversation(
                            source_id=source.source_id,
                            conversation_id=candidate["conversation_id"],
                            records=len(eligible),
                            characters=characters,
                            reason=reason,
                        )
                    )
                    continue
                used += characters
                for row in eligible:
                    clean = sanitize_model_input(row["verbatim"])
                    result.records.append(
                        SampleRecord(
                            evidence_id=row["evidence_id"],
                            source_id=row["source_id"],
                            conversation_id=row["conversation_id"],
                            role=row["role"],
                            written_by=row["written_by"],
                            created_at=row["created_at"],
                            observed_at=row["updated_at"],
                            revision=row["revision"],
                            content_hash=row["content_hash"],
                            workspace=row["workspace"],
                            project=row["project"],
                            text=clean,
                        )
                    )
                    source.selected_records += 1
        result.omitted_records = sum(item.records for item in result.deferred_conversations)
        result.coverage_complete = not result.deferred_conversations
        return result
