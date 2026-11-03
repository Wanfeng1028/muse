"""A1-08: audit which SQLite files under One Memory Home are MemHub's and which
are a vendor's.

Per D56 the business store is SQLite (overriding D53's MySQL-only decision), so
`one-memory.sqlite3` is now MemHub's own *and* the authority. The audit still
matters: "an Adapter may read the host's own SQLite", and a bundled vendor may
own its own store, so every SQLite file under One Memory Home must have a named
owner rather than being swept into the business database. It classifies each
file by location and names the owner.

Measured on this machine (2026-09-26), under `~/.one-memory`:

- `one-memory.sqlite3`  — MemHub's own business database; under D56 it is the
  SQLite authority.
- `hy-memory/**`        — the HY SDK's own store (governed history, cache,
  coding, and Chroma's vector index). D53 does not make these MemHub's, and
  this module must not pretend otherwise: they are declared as vendor-owned.

The classification is by location, which is the only signal available without
opening each file; and opening them would mean reading a vendor's private
schema, which is exactly what an audit should not need to do.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: MemHub's own business database, relative to One Memory Home.
MEMHUB_DB = "one-memory.sqlite3"

#: Prefixes a bundled vendor owns. Not MemHub's; not to be migrated by A1.
VENDOR_PREFIXES: tuple[str, ...] = ("hy-memory/",)

#: Prefixes an adapter may hold for a *host* app's own database. D53 keeps an
#: Adapter's right to read the host's own SQLite, so these are neither MemHub's
#: nor a bundled vendor's — they are the host's, borrowed. Reporting them as
#: UNKNOWN would imply nobody owns them, which is how a borrowed file survives a
#: migration and then quietly becomes the authority.
HOST_PREFIXES: tuple[str, ...] = ("snapshots/", "imports/snapshots/")


class Owner:
    MEMHUB = "memhub"
    VENDOR = "vendor"
    HOST = "host"
    UNKNOWN = "unknown"


#: Extensions that may be SQLite. A vendor might use another name, so this is
#: a suffix hint rather than a rule: files are classified first by location.
SQLITE_SUFFIXES: tuple[str, ...] = (".sqlite3", ".sqlite", ".db")


@dataclass(frozen=True)
class SqliteFile:
    #: Path relative to One Memory Home.
    relative: str
    owner: str
    #: Why this owner was chosen, so the audit can be reviewed rather than
    #: trusted.
    reason: str


def classify(relative: str) -> SqliteFile:
    """Classify one path under One Memory Home."""
    normalized = relative.replace("\\", "/").lstrip("./")
    if normalized == MEMHUB_DB:
        return SqliteFile(normalized, Owner.MEMHUB, "MemHub's own business database")
    for prefix in VENDOR_PREFIXES:
        if normalized.startswith(prefix):
            return SqliteFile(
                normalized,
                Owner.VENDOR,
                f"inside a bundled vendor's own directory ({prefix.rstrip('/')})",
            )
    for prefix in HOST_PREFIXES:
        if normalized.startswith(prefix):
            return SqliteFile(
                normalized,
                Owner.HOST,
                "a host app's own database held by an adapter (D53); not MemHub's "
                "to migrate, and not a bundled vendor's",
            )
    return SqliteFile(
        normalized,
        Owner.UNKNOWN,
        "not MemHub's database and not under a known vendor directory",
    )


def audit(home: str | Path) -> list[SqliteFile]:
    """Find and classify every candidate SQLite file under One Memory Home."""
    base = Path(home)
    found: list[SqliteFile] = []
    if not base.exists():
        return found
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if not path.name.endswith(SQLITE_SUFFIXES):
            continue
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:
            continue
        found.append(classify(relative))
    return found


def memhub_files(home: str | Path) -> list[SqliteFile]:
    """Files MemHub owns and must therefore migrate off SQLite."""
    return [item for item in audit(home) if item.owner == Owner.MEMHUB]


def vendor_files(home: str | Path) -> list[SqliteFile]:
    """Files a bundled vendor owns. Out of scope for migration, by D53."""
    return [item for item in audit(home) if item.owner == Owner.VENDOR]


def host_files(home: str | Path) -> list[SqliteFile]:
    """A host app's own database, held by an adapter. Not ours to migrate."""
    return [item for item in audit(home) if item.owner == Owner.HOST]


def unexplained_files(home: str | Path) -> list[SqliteFile]:
    """Files nobody owns on paper. These are the ones that need a decision.

    An unknown file is not automatically MemHub's — it might be a host app's
    snapshot left by an adapter, or a stray from an older build. It is reported
    rather than silently ignored, because "we did not know about it" is how a
    file survives a migration and then quietly becomes the authority.
    """
    return [item for item in audit(home) if item.owner == Owner.UNKNOWN]
