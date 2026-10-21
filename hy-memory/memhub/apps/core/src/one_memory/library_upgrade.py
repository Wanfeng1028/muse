"""The first thing a Core start does to the library: back it up if this start will rewrite it.

It runs before any store is constructed, through a read-only connection, so
the backup is the library exactly as it was found — journal mode, header and
every table an earlier version left. A store opening first cannot make that
true: each one adds its own tables and indexes, and the governance store
switches the file to WAL before anything else.

Only an upgrade that rewrites rows the person wrote is backed up. Today that
is the removal of pending and rejected memories; a library without them is
left alone and gets no backup.
"""

import hashlib
import sqlite3
import threading
import weakref
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from one_memory.memory_server.store_binding import store_for

#: States older versions wrote and nothing writes any more.
LEGACY_STATUSES = ("candidate", "rejected")
#: The operations that went with them.
LEGACY_OPERATIONS = ("confirm", "reject")

_LEGACY_STATUSES_IN = "(" + ",".join(f"'{status}'" for status in LEGACY_STATUSES) + ")"
_LEGACY_OPERATIONS_IN = "(" + ",".join(f"'{operation}'" for operation in LEGACY_OPERATIONS) + ")"


class LibraryUpgradeError(RuntimeError):
    """An upgrade that did not start, the library untouched, and what to do about it."""

    def __init__(self, code: str, *, reason: str, remedy: str) -> None:
        super().__init__(f"{code}: {reason}. {remedy}")
        self.code = code
        self.reason = reason
        self.remedy = remedy


_SQLITE_HEADER = b"SQLite format 3\x00"


@dataclass(frozen=True, eq=False)
class PreparedLibrary:
    """Proof that this library went through the step below before anything opened it.

    Only `prepare_library` issues one, and it is good for one store: a proof
    built by hand, or handed to a second store, lets nothing be rewritten.
    """

    database_path: Path
    #: None when there was nothing to upgrade, so nothing to back up.
    backup: Path | None

    def consume(self, database_path: Path) -> bool:
        """Whether this library may be rewritten now: issued for it, unused, backup intact.

        A backup that is gone or damaged by now raises instead: rewriting
        would leave the person with no way back.
        """
        with _issued_lock:
            # Only an issued proof with a backup has a digest to take.
            digest = _issued.pop(self, None)
        if digest is None or self.backup is None or self.database_path != database_path.resolve():
            return False
        problem = _backup_problem(self.backup, digest)
        if problem is not None:
            raise LibraryUpgradeError(
                "library_upgrade_backup_unusable",
                reason=f"the backup made before upgrading is no longer usable ({problem})",
                remedy=(
                    f"Nothing in {database_path} was changed. Leave {self.backup.parent} "
                    "alone and start MemHub again: a new backup is made first."
                ),
            )
        return True


#: Every proof issued and not yet used, with the digest of the backup it
#: was issued for: a sound SQLite file put in its place restores nothing.
_issued: "weakref.WeakKeyDictionary[PreparedLibrary, str | None]" = weakref.WeakKeyDictionary()
_issued_lock = threading.Lock()


def _issue(database_path: Path, backup: Path | None, digest: str | None) -> PreparedLibrary:
    prepared = PreparedLibrary(database_path, backup)
    with _issued_lock:
        _issued[prepared] = digest
    return prepared


def _digest(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _backup_problem(backup: Path, digest: str) -> str | None:
    """Why this file cannot restore the library, or None when it can."""
    try:
        if _digest(backup) != digest:
            return "it is not the file that was backed up"
        with backup.open("rb") as file:
            if file.read(len(_SQLITE_HEADER)) != _SQLITE_HEADER:
                return "not a SQLite database"
        # The finished copy has no journal to read. Without `immutable` a
        # WAL-mode copy grows -wal/-shm files beside it, not owner-only.
        with closing(sqlite3.connect(f"{backup.as_uri()}?mode=ro&immutable=1", uri=True)) as db:
            verdict = [row[0] for row in db.execute("PRAGMA quick_check")]
    except (OSError, sqlite3.Error) as error:
        return str(error)
    return None if verdict == ["ok"] else "; ".join(verdict[:3])


def holds_legacy_rows(connection: sqlite3.Connection) -> bool:
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    checks = {
        "governed_memories": "SELECT 1 FROM governed_memories "
        f"WHERE status IN {_LEGACY_STATUSES_IN}",
        "governed_memory_versions": "SELECT 1 FROM governed_memory_versions "
        f"WHERE status IN {_LEGACY_STATUSES_IN} OR action IN {_LEGACY_OPERATIONS_IN}",
        "governed_memory_mutations": "SELECT 1 FROM governed_memory_mutations "
        f"WHERE operation IN {_LEGACY_OPERATIONS_IN}",
    }
    present = [query for table, query in checks.items() if table in tables]
    if not present:
        return False
    return connection.execute(" UNION ALL ".join(present) + " LIMIT 1").fetchone() is not None


def prepare_library(database_path: Path) -> PreparedLibrary:
    """Back the library up if it holds rows this version rewrites; change nothing in it.

    A backup that cannot be made stops the upgrade: the library is left as it
    was and the error says why and what to do, so the next start can succeed.
    """
    resolved = database_path.resolve()
    if not database_path.exists():
        return _issue(resolved, None, None)
    database: Any = store_for(database_path)
    with database.read() as connection:
        if not holds_legacy_rows(connection):
            return _issue(resolved, None, None)
    directory = database_path.parent / "backups"
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    target = directory / f"pre-drop-candidate-{stamp}.sqlite3"
    try:
        database.back_up(target)
        digest = _digest(target)
    except (OSError, sqlite3.Error) as error:
        raise LibraryUpgradeError(
            "library_upgrade_backup_failed",
            reason=f"the library could not be backed up before upgrading ({error})",
            remedy=(
                f"Nothing in {database_path} was changed. Make sure {directory} is a "
                "writable folder on a disk with free space, then start MemHub again."
            ),
        ) from error
    return _issue(resolved, target, digest)
