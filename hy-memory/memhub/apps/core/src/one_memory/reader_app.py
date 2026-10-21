"""Read-only process: serves the same read routes as Core without write access.

Opens the database in `mode=ro` with `PRAGMA query_only=ON`; every store
operation here goes through `main_database().read()`, which already enforces
this. No HY SDK, no Chroma, no ONNX runtime, no keychain: the imports that
would pull them in are simply not reached, and the routes below never call
into a write path.

Reads that need HY (semantic search, graph overlay) are delegated to the
Core's internal endpoints; the Core is the only process that owns the
vector stores. Side effects (call events, feedback) are queued and sent
asynchronously, never blocking the read response.
"""

from __future__ import annotations

import asyncio
import builtins
import contextlib
import logging
import os
import sqlite3
import time
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, SecretStr

from one_memory.database_access import main_database
from one_memory.home_summary import (
    HomeSummary,
    HomeSummaryUnavailable,
    read_home_summary,
)
from one_memory.memory_governance import GovernedMemory, MemoryStatus
from one_memory.memory_library import MemoryLibraryPage, read_memory_library
from one_memory.recall import RecallRequest, _KeywordCandidates
from one_memory.semantic_deadline import SemanticMemoryHit
from one_memory.source_read_access import SourceReadAccess

logger = logging.getLogger(__name__)

MAX_READER_RSS_BYTES = 250 * 1024 * 1024

_PROBE_QUERY = "__om_probe__"


def _check_imports() -> None:
    """Fail fast if any forbidden module is already loaded."""
    forbidden = ("hy_memory", "chromadb", "onnxruntime", "keyring")
    import sys

    loaded = [name for name in forbidden if name in sys.modules]
    if loaded:
        raise ImportError(f"reader_process_loaded_forbidden_modules: {', '.join(loaded)}")


def _memory_readable_sql() -> str:
    return """
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


class ReaderSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 0  # 0 = ephemeral
    api_token: SecretStr
    core_port: int
    core_api_token: str


class SideEffectForwarder:
    """Queues read-path side effects and forwards them to Core.

    Reads in the Reader must stay read-only: the database is opened with
    `query_only`, so a call event cannot be written here. Instead each read
    that would have recorded one enqueues it, and a background task posts it
    to Core's internal endpoint. The response never waits for it; a Core that
    is unavailable drops it and counts the drop.
    """

    def __init__(self, settings: ReaderSettings) -> None:
        self.settings = settings
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=256)
        self.dropped = 0
        self.task: asyncio.Task[None] | None = None

    def enqueue(self, event: dict[str, object]) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.ensure_future(self._drain())

    def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()

    async def _drain(self) -> None:
        import httpx

        while True:
            event = await self.queue.get()
            try:
                async with httpx.AsyncClient(
                    headers={
                        "Authorization": f"Bearer {self.settings.core_api_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=5.0,
                    proxy=None,
                ) as client:
                    await client.post(
                        f"http://127.0.0.1:{self.settings.core_port}/internal/call-event",
                        json=event,
                    )
            except Exception:
                # A dropped side effect is never a failed read: recall already
                # answered. Counted so a persistently unavailable Core is
                # visible rather than silent.
                self.dropped += 1


async def _core_get(
    settings: ReaderSettings,
    path: str,
    timeout_s: float = 5.0,
    params: Mapping[
        str, str | int | float | bool | None | Sequence[str | int | float | bool | None]
    ]
    | None = None,
) -> Any:
    """Call the Core's internal read endpoint for data only Core can serve.

    `params` is passed to httpx rather than interpolated into the path: a
    query containing `&`, `#` or a space would otherwise be cut short or
    read as a fragment, silently searching for the wrong thing.
    """
    import httpx

    url = f"http://127.0.0.1:{settings.core_port}{path}"
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {settings.core_api_token}"},
        timeout=timeout_s,
        proxy=None,
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


class _ReaderGovernance:
    """Minimal read interface over the governance store for recall."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def list(
        self,
        *,
        user_id: str,
        status: MemoryStatus | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GovernedMemory]:
        """One page of memories, read through the Core's own read function.

        `MemoryGovernanceStore.list` cannot be used directly: constructing the
        store runs schema DDL on the write connection, and the Reader opens
        with `query_only`. `read_memory_library` is the same read expressed as
        a static SQL read (revoked sources excluded, per-row freshness checked
        for the rows it returns, cheap total for the rest), so the Reader and
        the Core cannot drift on what "readable" means.
        """
        page = read_memory_library(
            self.database_path,
            user_id=user_id,
            query=query,
            status=status,
            offset=offset,
            limit=limit,
        )
        return list(page.items)

    def find_confirmed_matching_terms(
        self,
        *,
        user_id: str,
        terms: Collection[str],
        limit: int = 200,
        scopes: Collection[str] | None = None,
    ) -> tuple[builtins.list[GovernedMemory], bool]:
        if not 1 <= limit <= 2_000:
            raise ValueError("invalid candidate limit")
        cleaned = tuple(dict.fromkeys(term.strip() for term in terms if term.strip()))
        if not cleaned or scopes is not None and not scopes:
            return [], False
        clauses = ["m.user_id=?", "m.status='confirmed'", "m.deleted_at IS NULL"]
        values: builtins.list[object] = [user_id]
        matches = []
        for term in cleaned[:32]:
            matches.append("m.content LIKE ? ESCAPE '\\'")
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            values.append(f"%{escaped}%")
        clauses.append(f"({' OR '.join(matches)})")
        if scopes is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(m.scopes_json) "
                f"WHERE json_each.value IN ({','.join('?' for _ in scopes)}))"
            )
            values.extend(scopes)
        values.append(limit + 1)
        with main_database(self.database_path).read(row_factory=sqlite3.Row) as db:
            rows = db.execute(
                f"SELECT m.* FROM governed_memories m WHERE {' AND '.join(clauses)} "
                "ORDER BY m.updated_at DESC,m.memory_id LIMIT ?",
                values,
            ).fetchall()
            items = self._memories_from_rows(db, rows[:limit])
        return items, len(rows) > limit or len(cleaned) > 32

    def get(self, memory_id: str, *, user_id: str) -> GovernedMemory | None:
        memory = _get_memory_direct(self.database_path, memory_id, user_id)
        return memory if isinstance(memory, GovernedMemory) else None

    def sources_behind_memories(
        self,
        *,
        user_id: str,
        memory_ids: Collection[str],
    ) -> dict[str, frozenset[str]]:
        if not memory_ids:
            return {}
        identifiers = tuple(memory_ids)
        placeholders = ",".join("?" for _ in identifiers)
        with main_database(self.database_path).read(row_factory=sqlite3.Row) as db:
            rows = db.execute(
                "SELECT link.memory_id,e.source_id FROM governed_memory_evidence link "
                "JOIN evidence e ON e.evidence_id=link.evidence_id "
                f"WHERE link.active=1 AND e.user_id=? AND link.memory_id IN ({placeholders})",
                (user_id, *identifiers),
            ).fetchall()
        found: dict[str, set[str]] = {}
        for row in rows:
            found.setdefault(str(row["memory_id"]), set()).add(str(row["source_id"]))
        return {key: frozenset(values) for key, values in found.items()}

    @staticmethod
    def _memories_from_rows(
        db: sqlite3.Connection, rows: Sequence[sqlite3.Row]
    ) -> builtins.list[GovernedMemory]:
        from one_memory.memory_governance import MemoryGovernanceStore

        return MemoryGovernanceStore.memories_from_rows(db, builtins.list(rows))


def _conversation_hit(row: Any) -> dict[str, Any]:
    """One stored row as a search hit.

    The author travels with the row. A client that is not told who wrote a row
    has to invent an author, and the invention is always "the user", which
    files an assistant turn under the person who was talking to it.
    """
    return {
        "evidence_id": row["evidence_id"],
        "conversation_id": row["conversation_id"],
        "source_id": row["source_id"],
        "workspace": row["workspace"],
        "project": row["project"],
        "created_at": row["created_at"],
        "excerpt": row["verbatim"][:200] if row["verbatim"] else "",
        # Both columns are NOT NULL on `evidence`, so a stored row always
        # knows; a summary of a whole conversation has no single author and
        # never reaches here.
        "role": row["role"],
        "written_by": row["written_by"],
    }


def create_reader_app(settings: ReaderSettings) -> FastAPI:
    """A read-only FastAPI application for the Reader process."""
    _check_imports()
    database_path = settings.data_dir / "one-memory.sqlite3"
    if not database_path.exists():
        raise FileNotFoundError(f"reader_database_missing: {database_path}")

    # Validate schema version without writing.
    from one_memory.memory_server.migrations import SCHEMA_TABLE
    from one_memory.schema_gate import BUILD_SCHEMA_VERSION

    with main_database(database_path).read() as db:
        tables = {
            str(row[0]) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if SCHEMA_TABLE in tables:
            row = db.execute(f"SELECT MAX(version) FROM {SCHEMA_TABLE}").fetchone()
            found = int(row[0]) if row and row[0] is not None else 0
            if found > BUILD_SCHEMA_VERSION:
                raise RuntimeError(f"reader_schema_too_new: {found} > {BUILD_SCHEMA_VERSION}")
        elif not tables:
            raise RuntimeError("reader_database_empty")

    access = SourceReadAccess(database_path)
    forwarder = SideEffectForwarder(settings)
    governance = _ReaderGovernance(database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        monitor = asyncio.get_running_loop().create_task(_memory_monitor())
        forwarder.start()
        yield
        monitor.cancel()
        forwarder.stop()

    async def _memory_monitor() -> None:
        import resource
        import sys

        while True:
            await asyncio.sleep(30)
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_bytes = usage if sys.platform == "darwin" else usage * 1024
            if rss_bytes > MAX_READER_RSS_BYTES:
                logger.error(
                    "reader_memory_limit_exceeded: %d bytes > %d",
                    rss_bytes,
                    MAX_READER_RSS_BYTES,
                )
                os._exit(1)

    app = FastAPI(title="MemHub Reader", lifespan=lifespan)
    app.state.settings = settings
    app.state.database_path = database_path

    expected_token = settings.api_token.get_secret_value()

    def require_auth(request: Request) -> None:
        import hmac

        origin = request.headers.get("origin")
        if origin is not None and origin not in (
            "one-memory://app",
            "http://localhost:5173",
        ):
            raise HTTPException(403, "origin_not_allowed")
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if not (scheme.lower() == "bearer" and hmac.compare_digest(token, expected_token)):
            raise HTTPException(401, "invalid_local_token")

    protected = [Depends(require_auth)]

    @app.get("/api/v1/home-summary", response_model=HomeSummary, dependencies=protected)
    def home_summary() -> HomeSummary:
        try:
            return read_home_summary(database_path)
        except HomeSummaryUnavailable:
            # Belt and braces: read_home_summary answers stale itself, but if
            # that ever changes, never let the homepage 500.
            return HomeSummary(
                memory_count=0, latest=None, observed_at=datetime.now(UTC), stale=True
            )

    @app.get("/api/v1/memory-library", response_model=MemoryLibraryPage, dependencies=protected)
    def memory_library(
        query: str | None = Query(default=None, max_length=512),
        status: str | None = None,
        active_only: bool = False,
        source: str | None = Query(default=None, min_length=1),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> MemoryLibraryPage:
        from one_memory.memory_governance import MemoryStatus as MS

        ms = MS(status) if status else None
        return read_memory_library(
            database_path,
            user_id="local",
            query=query,
            status=ms,
            active_only=active_only,
            source=source,
            offset=offset,
            limit=limit,
        )

    @app.get("/api/v1/memories", dependencies=protected)
    def list_memories(
        status: str | None = None,
        query: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        from one_memory.memory_governance import MemoryStatus as MS

        ms = MS(status) if status else None
        memories = governance.list(
            user_id="local", status=ms, query=query, limit=limit, offset=offset
        )
        visible = access.memories(memories)
        return [m.model_dump(mode="json") for m in visible]

    @app.get("/api/v1/memories/graph", dependencies=protected)
    async def memory_graph(
        limit: int = Query(default=160, ge=1, le=300),
    ) -> dict[str, Any]:
        memories = governance.list(user_id="local", status=MemoryStatus.CONFIRMED, limit=500)
        projected = access.memories(memories[:limit])
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        source_ids: set[str] = set()
        with main_database(database_path).read(row_factory=sqlite3.Row) as db:
            for memory in projected:
                node_id = f"memory:{memory.memory_id}"
                nodes[node_id] = {
                    "node_id": node_id,
                    "node_type": "memory",
                    "label": memory.content,
                    "memory_id": memory.memory_id,
                    "kind": memory.kind.value
                    if hasattr(memory.kind, "value")
                    else str(memory.kind),
                    "status": memory.status.value
                    if hasattr(memory.status, "value")
                    else str(memory.status),
                }
                evidence_ids = list(memory.evidence_ids)
                if evidence_ids:
                    placeholders = ",".join("?" for _ in evidence_ids)
                    sql = (
                        f"SELECT DISTINCT source_id FROM evidence"
                        f" WHERE evidence_id IN ({placeholders})"
                    )
                    for row in db.execute(
                        sql,
                        evidence_ids,
                    ):
                        sid = str(row["source_id"])
                        source_ids.add(sid)
            for sid in sorted(source_ids):
                source_node_id = f"source:{sid}"
                nodes[source_node_id] = {
                    "node_id": source_node_id,
                    "node_type": "source",
                    "label": sid,
                    "source_id": sid,
                }
                for memory in projected:
                    if any(_source_for_evidence(db, eid) == sid for eid in memory.evidence_ids):
                        memory_node_id = f"memory:{memory.memory_id}"
                        edges.append(
                            {
                                "edge_id": f"{source_node_id}->{memory_node_id}",
                                "source_node_id": source_node_id,
                                "target_node_id": memory_node_id,
                            }
                        )
        # Fetch HY graph overlay from Core (not available in Reader).
        hy_overlay = None
        with contextlib.suppress(Exception):
            hy_overlay = await _core_get(
                settings,
                "/internal/graph-snapshot",
                timeout_s=5.0,
                params={"limit": limit},
            )
        if hy_overlay and not hy_overlay.get("consulted", False):
            hy_overlay = None
        return {
            "limit": limit,
            "total": len(projected),
            "nodes": tuple(nodes.values()),
            "edges": edges,
            **({"hy_overlay": hy_overlay} if hy_overlay else {}),
        }

    @app.get("/api/v1/memories/{memory_id}", dependencies=protected)
    def get_memory(memory_id: str) -> dict[str, Any]:
        memory = _get_memory_direct(database_path, memory_id, "local")
        if memory is None:
            raise HTTPException(404, "memory_not_found")
        if not access.memories([memory]):
            raise HTTPException(403, "memory_source_revoked")
        return cast(dict[str, Any], memory.model_dump(mode="json"))

    @app.post("/api/v1/recall", response_model=None, dependencies=protected)
    async def recall(request: RecallRequest) -> dict[str, Any]:
        from one_memory.recall import GovernedRecallTarget

        started = time.monotonic()
        target = GovernedRecallTarget(
            governance=governance,
            semantic_search=None,
            resolve_workspace=None,
            filter_memories=access.memories,
        )

        if request.query == _PROBE_QUERY:
            return target.recall(request, user_id="local").model_dump(mode="json")
        deadline = time.monotonic() + request.timeout_ms / 1_000
        semantic_ids: tuple[str, ...] = ()
        try:
            remaining = max(0.1, deadline - time.monotonic())
            result = await asyncio.wait_for(
                _core_get(
                    settings,
                    "/internal/semantic-ids",
                    timeout_s=remaining,
                    params={"query": request.query, "limit": request.limit},
                ),
                timeout=remaining,
            )
            semantic_ids = tuple(str(value) for value in result.get("ids", []) if value)
        except Exception:
            pass
        readable = target._readable_scopes(request)
        # Keyword candidates from read-only SQL.
        keywords = target._keyword_candidates(
            request, user_id="local", readable=readable, deadline=deadline
        )
        receipt = target._rank(
            request,
            user_id="local",
            readable=readable,
            semantic_hits={
                memory_id: SemanticMemoryHit(
                    memory_id,
                    1.0 - index / max(1, len(semantic_ids)),
                )
                for index, memory_id in enumerate(semantic_ids)
            },
            keywords=keywords
            if isinstance(keywords, _KeywordCandidates)
            else _KeywordCandidates((), False, False),
            deadline=deadline,
            timed_out=False,
        )
        forwarder.enqueue(
            {
                "tool": "om_recall",
                "query": request.query,
                "scope": request.scope,
                "state": receipt.state.value,
                "memory_count": len(receipt.hits),
                "elapsed_ms": (time.monotonic() - started) * 1000,
            }
        )
        return receipt.model_dump(mode="json")

    @app.get("/api/v1/conversations/search", dependencies=protected)
    def search_conversations(
        query: str = Query(min_length=1, max_length=512),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        if not database_path.exists():
            raise HTTPException(503, "conversation_search_unavailable")
        with main_database(database_path).read(row_factory=sqlite3.Row) as db:
            try:
                rows = db.execute(
                    """SELECT * FROM evidence
                    WHERE user_id = 'local' AND verbatim LIKE ? ESCAPE '\\'
                    ORDER BY imported_at DESC LIMIT ?""",
                    (f"%{query}%", limit),
                ).fetchall()
            except Exception:
                raise HTTPException(503, "conversation_search_unavailable") from None
        hits = [_conversation_hit(row) for row in rows]
        return {
            "hits": hits,
            "empty_reason": None if hits else "no_matches",
            "imported_messages": len(hits),
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "one-memory-reader"}

    return app


def _get_memory_direct(database_path: Path, memory_id: str, user_id: str) -> Any:
    from one_memory.memory_governance import _memory_from_row, _memory_links

    with main_database(database_path).read(row_factory=sqlite3.Row) as db:
        row = db.execute(
            "SELECT * FROM governed_memories WHERE memory_id = ? AND user_id = ?",
            (memory_id, user_id),
        ).fetchone()
        if row is None:
            return None
        links = _memory_links(db, [memory_id])
        return _memory_from_row(row, *(tuple(vals) for vals in links[memory_id]))


def _source_for_evidence(db: sqlite3.Connection, evidence_id: str) -> str | None:
    row = db.execute(
        "SELECT source_id FROM evidence WHERE evidence_id = ?", (evidence_id,)
    ).fetchone()
    return str(row["source_id"]) if row else None
