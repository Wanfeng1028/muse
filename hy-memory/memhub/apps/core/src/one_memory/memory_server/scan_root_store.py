"""A4-01: persisted scan-root configuration.

`scan_roots.py` decides the rules without touching a filesystem; this is the
half that keeps them across a restart, so a registered directory does not
silently vanish and leave the user wondering why nothing is being imported.

The document is stored as one JSON row rather than a row per root: the config is
read as a unit and every mutation bumps the revision, so a partial write could
not be told from a complete one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from one_memory.memory_server.scan_roots import (
    ScanRoot,
    ScanRootConfig,
    canonical,
    is_blank,
    validate,
)
from one_memory.memory_server.store_binding import store_for

TABLE = "scan_root_config"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    config_json TEXT NOT NULL
)
"""


def _is_mysql(store: Any) -> bool:
    from one_memory.memory_server.sync_facade import SyncStoreFacade

    return isinstance(store, SyncStoreFacade)


def _value(row: object, index: int) -> object:
    """Read a column from either a sqlite3.Row or a plain tuple."""
    try:
        return row[index]  # type: ignore[index]
    except (TypeError, KeyError):
        return row[index]  # type: ignore[index]


def new_root_id(path: str, source_id: str | None) -> str:
    """A stable id for one directory, so add and remove address the same root.

    Derived from the path and source rather than random: registering the same
    directory twice has to be refused (see `scan_roots.validate`), and a random
    id would let the duplicate through and sweep the directory twice.
    """
    basis = f"{source_id or ''}|{canonical(path)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _decode(raw: object) -> ScanRootConfig:
    if raw is None:
        return ScanRootConfig()
    try:
        document = json.loads(str(raw))
    except (TypeError, ValueError):
        # Treated as no configuration rather than a crash: the user can register
        # roots again, and refusing to start over one odd settings row is worse.
        return ScanRootConfig()
    if not isinstance(document, dict):
        return ScanRootConfig()
    roots = []
    for item in document.get("roots", []):
        if not isinstance(item, dict):
            continue
        roots.append(
            ScanRoot(
                root_id=str(item.get("root_id", "")),
                path=canonical(str(item.get("path", ""))),
                source_id=(str(item["source_id"]) if item.get("source_id") is not None else None),
                recursive=bool(item.get("recursive", True)),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return ScanRootConfig(roots=tuple(roots), revision=int(document.get("revision", 0)))


class ScanRootStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._store = store_for(database_path)

    def initialize(self) -> None:
        with self._store.write() as connection:
            connection.execute(SCHEMA)

    def get(self) -> ScanRootConfig:
        with self._store.write() as connection:
            connection.execute(SCHEMA)
            rows = connection.execute(f"SELECT config_json FROM {TABLE} WHERE singleton = 1")
            row = rows.fetchone() if hasattr(rows, "fetchone") else _first(rows)
        return _decode(_value(row, 0)) if row is not None else ScanRootConfig()

    def save(self, config: ScanRootConfig) -> ScanRootConfig:
        problems = validate(config)
        if problems:
            raise ValueError("; ".join(problems))
        payload = json.dumps(
            {
                "revision": config.revision,
                "roots": [
                    {
                        "root_id": root.root_id,
                        "path": root.path,
                        "source_id": root.source_id,
                        "recursive": root.recursive,
                        "enabled": root.enabled,
                    }
                    for root in config.roots
                ],
            }
        )
        with self._store.write() as connection:
            connection.execute(SCHEMA)
            if _is_mysql(self._store):
                connection.execute(
                    f"INSERT INTO {TABLE} (singleton, config_json) VALUES (1, %s) "
                    "ON DUPLICATE KEY UPDATE config_json = VALUES(config_json)",
                    (payload,),
                )
            else:
                connection.execute(
                    f"INSERT INTO {TABLE} (singleton, config_json) VALUES (1, ?) "
                    "ON CONFLICT(singleton) DO UPDATE SET config_json = excluded.config_json",
                    (payload,),
                )
            # Committed here, not left to the checkout: a writer handed back
            # through the pool is rolled back rather than committed, so an
            # implicit commit would silently discard the registration and the
            # user would see the root disappear on the next read.
            connection.commit()
        return config


def _first(rows: Any) -> Any:
    if rows is None:
        return None
    try:
        for row in rows:
            return row
    except TypeError:
        return None


def blank(path: str) -> bool:
    return is_blank(path)
