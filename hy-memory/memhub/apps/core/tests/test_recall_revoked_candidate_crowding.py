"""Revoked-source rows must not crowd a readable recall hit out of the page."""

from __future__ import annotations

from one_memory.memory_governance import MemoryGovernanceStore
from one_memory.recall import GovernedRecallTarget, RecallRequest, RecallState

REVOKED_MATCHES = 260


def test_revoked_rows_do_not_hide_a_readable_match(tmp_path):
    database = tmp_path / "one-memory.sqlite3"
    governance = MemoryGovernanceStore(database)
    # Same timestamp on every row, so the candidate order is the SQL
    # tie-breaker `memory_id`; the 260 blocked rows sort ahead of the one
    # readable row.
    now = "2026-09-01T00:00:00+00:00"
    with governance._connection() as connection:
        connection.executemany(
            "INSERT INTO governed_memories (memory_id,user_id,kind,status,content,"
            "scopes_json,revision,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    f"aaa-{index:04d}",
                    "local",
                    "chat",
                    "confirmed",
                    f"shared target revoked {index}",
                    '["all-apps"]',
                    1,
                    now,
                    now,
                )
                for index in range(REVOKED_MATCHES)
            ]
            + [
                (
                    "zzz-readable",
                    "local",
                    "chat",
                    "confirmed",
                    "shared target readable",
                    '["all-apps"]',
                    1,
                    now,
                    now,
                )
            ],
        )

    def block_revoked(memories):
        return [memory for memory in memories if not memory.memory_id.startswith("aaa-")]

    receipt = GovernedRecallTarget(governance, filter_memories=block_revoked).recall(
        RecallRequest(query="shared target")
    )

    assert receipt.state is RecallState.GROUNDED
    assert {hit.memory_id for hit in receipt.hits} == {"zzz-readable"}
    assert not {hit.memory_id for hit in receipt.hits if hit.memory_id.startswith("aaa-")}
