"""Bounded, permission-aware receipt projection; never initialize a write store."""

import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from one_memory.database_access import main_database

#: `legacy` is a confirmation recorded before memories stopped waiting for
#: one; it changed nothing that still exists, and `migrated_from` says so.
Operation = Literal["create", "correct", "set_scopes", "undo", "delete", "hy_reconcile", "legacy"]
ResultStatus = Literal["confirmed", "deleted"]
MigratedFrom = Literal["confirm", "reject"]
OPERATIONS = {"create", "correct", "set_scopes", "undo", "delete", "hy_reconcile", "legacy"}
STATUSES = {"confirmed", "deleted"}
#: Which operation each pre-v2 one now reads as.
MIGRATED_OPERATIONS = {"confirm": "legacy", "reject": "delete"}
#: A memory may move on to these after an earlier receipt was written; the
#: receipt still reports what that request committed, not the current status.
CURRENT_STATUSES = STATUSES | {"superseded"}


class MemoryMutationReceiptForbidden(RuntimeError):
    def __init__(self) -> None:
        super().__init__("memory_mutation_receipt_forbidden")


class MemoryMutationReceiptUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("memory_mutation_receipt_unavailable")


class MemoryMutationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[2] = 2
    request_id: str
    state: Literal["not_found", "committed"]
    operation: Operation | None = None
    memory_id: str | None = None
    result_revision: int | None = None
    result_status: ResultStatus | None = None
    memory_state: Literal["present", "deleted"] | None = None
    #: The operation as it was stored before v2, when it has no v2 name of its own.
    migrated_from: MigratedFrom | None = None


def _identity(value: str, maximum: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= maximum


def _read_snapshot(
    database_path: Path, request_id: str, user_id: str
) -> tuple[MemoryMutationReceipt, tuple[object, ...]]:
    with main_database(database_path).read(row_factory=sqlite3.Row) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        rows = db.execute(
            "SELECT user_id,request_id,memory_id,operation,result_revision "
            "FROM governed_memory_mutations WHERE user_id=? AND request_id=? LIMIT 2",
            (user_id, request_id),
        ).fetchall()
        if not rows:
            return MemoryMutationReceipt(request_id=request_id, state="not_found"), ()
        if len(rows) != 1:
            raise MemoryMutationReceiptUnavailable()
        mutation = rows[0]
        memory_id, operation, revision = (
            mutation["memory_id"],
            mutation["operation"],
            mutation["result_revision"],
        )
        if (
            not _identity(memory_id, 512)
            or operation not in OPERATIONS
            or type(revision) is not int
            or not 1 <= revision <= 2**53 - 1
        ):
            raise MemoryMutationReceiptUnavailable()
        current = db.execute(
            "SELECT user_id,revision,status,deleted_at FROM governed_memories WHERE memory_id=?",
            (memory_id,),
        ).fetchone()
        if (
            current is None
            or current["user_id"] != user_id
            or type(current["revision"]) is not int
            or current["revision"] < revision
            or current["status"] not in CURRENT_STATUSES
            or (current["status"] == "deleted") != (current["deleted_at"] is not None)
        ):
            raise MemoryMutationReceiptUnavailable()

        # Versions have no historical evidence snapshot. Check every retained link,
        # not only active ones, before disclosing even operation/ID metadata.
        links = db.execute(
            "SELECT l.evidence_id,l.active,e.user_id,e.source_id,e.revision,"
            "g.granted_at,g.revoked_at FROM governed_memory_evidence l "
            "LEFT JOIN evidence e ON e.evidence_id=l.evidence_id "
            "LEFT JOIN source_grants g ON g.user_id=e.user_id AND g.source_id=e.source_id "
            "WHERE l.memory_id=? ORDER BY l.evidence_id LIMIT 10001",
            (memory_id,),
        ).fetchall()
        if not links or len(links) > 10000:
            raise MemoryMutationReceiptUnavailable()
        for link in links:
            if (
                link["user_id"] != user_id
                or link["source_id"] is None
                or link["active"] not in (0, 1)
            ):
                raise MemoryMutationReceiptUnavailable()
            if link["revoked_at"] is not None:
                raise MemoryMutationReceiptForbidden()
        versions = db.execute(
            "SELECT memory_id,revision,action,status,migrated_from FROM governed_memory_versions "
            "WHERE memory_id=? AND revision=? LIMIT 2",
            (memory_id, revision),
        ).fetchall()
        if len(versions) != 1:
            raise MemoryMutationReceiptUnavailable()
        version = versions[0]
        if version["action"] != operation or version["status"] not in STATUSES:
            raise MemoryMutationReceiptUnavailable()
        migrated_from = version["migrated_from"]
        if migrated_from is not None and MIGRATED_OPERATIONS.get(migrated_from) != operation:
            raise MemoryMutationReceiptUnavailable()
        if (operation == "legacy") != (migrated_from == "confirm"):
            raise MemoryMutationReceiptUnavailable()
        required_status = {
            "create": "confirmed",
            "legacy": "confirmed",
            "delete": "deleted",
        }
        if operation in required_status and version["status"] != required_status[operation]:
            raise MemoryMutationReceiptUnavailable()
        if (operation == "create") != (revision == 1):
            raise MemoryMutationReceiptUnavailable()
        if (
            operation in {"correct", "set_scopes", "hy_reconcile", "undo"}
            and version["status"] != "confirmed"
        ):
            raise MemoryMutationReceiptUnavailable()
        receipt = MemoryMutationReceipt(
            request_id=request_id,
            state="committed",
            operation=operation,
            memory_id=memory_id,
            result_revision=revision,
            result_status=version["status"],
            memory_state="deleted" if current["status"] == "deleted" else "present",
            migrated_from=migrated_from,
        )
        return receipt, (
            tuple(mutation),
            tuple(current),
            tuple(version),
            tuple(tuple(link) for link in links),
        )


def read_memory_mutation_receipt(
    database_path: Path, *, request_id: str, user_id: str = "local"
) -> MemoryMutationReceipt:
    """History only, never current authorization, HY cleanup or safe-retry proof."""
    if not _identity(request_id, 256):
        raise ValueError("invalid_memory_mutation_request_id")
    if not _identity(user_id, 256):
        raise ValueError("invalid_memory_mutation_user_id")
    try:
        first = _read_snapshot(database_path, request_id, user_id)
        current = _read_snapshot(database_path, request_id, user_id)
        if first != current:
            raise MemoryMutationReceiptUnavailable()
        return current[0]
    except MemoryMutationReceiptForbidden:
        raise
    except (sqlite3.Error, ValueError, TypeError, KeyError, IndexError, OSError):
        raise MemoryMutationReceiptUnavailable() from None
