"""Fuse lexical raw context with an optional derived index. No new HTTP schema."""

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from one_memory.context_models import (
    ContextLaneResult,
    ContextSearchRequest,
    ContextSemanticStatus,
    RawContextItem,
)
from one_memory.context_raw import (
    _METADATA,
    _check,
    _connection,
    _execute,
    _message,
    _readable,
    read_raw_context,
)
from one_memory.retrieval.models import TimeRange
from one_memory.retrieval.raw_candidates import RawCandidateBatch, compose_raw_retrieval_path


class RawIndexLookup(Protocol):
    def lookup_raw(
        self,
        query: str,
        *,
        source_ids: frozenset[str] | None,
        deadline: float,
        time_range: TimeRange | None = None,
    ) -> tuple[RawCandidateBatch, bool]: ...


def fuse_raw_lane(
    lexical: ContextLaneResult,
    batch: RawCandidateBatch,
    *,
    unpublished_authorized: bool,
    extra_items: tuple[RawContextItem, ...] = (),
) -> ContextLaneResult:
    """v1 has no coverage field; degraded + lexical_only stands in for partial index."""
    semantic_status: ContextSemanticStatus = (
        "timed_out"
        if batch.reason == "deadline"
        else "failed"
        if batch.reason in {"index_unavailable", "vector_unavailable"}
        else "completed"
    )
    index_complete = batch.complete and not unpublished_authorized
    timed_out = semantic_status == "timed_out"
    if lexical.status not in {"ok", "empty", "degraded"}:
        return lexical.model_copy(
            update={
                "searched_channels": ("lexical", "semantic"),
                "semantic_status": semantic_status,
                "index_complete": index_complete,
                "timed_out": timed_out,
            }
        )
    seen = {item.anchor_evidence_id for item in lexical.items if isinstance(item, RawContextItem)}
    extras = tuple(item for item in extra_items if isinstance(item, RawContextItem))
    # Semantic similarity is a candidate signal, not a verified recall result.
    # Release only semantic items that the lexical lane independently confirmed
    # for the same evidence identity. Unconfirmed semantic hits stay in the
    # coverage receipt as partial/degraded and must not reach host injection.
    unconfirmed_semantic = any(item.anchor_evidence_id not in seen for item in extras)
    items = lexical.items
    path = compose_raw_retrieval_path(
        batch,
        unpublished_authorized=unpublished_authorized,
        lexical_hit_count=len(lexical.items),
    )
    status = path.status
    if unconfirmed_semantic:
        status = "degraded"
    if lexical.status == "degraded" and status == "ok":
        status = "degraded"
    return ContextLaneResult(
        status=status,
        reason=(
            "lexical_only" if unconfirmed_semantic and lexical.reason is None else lexical.reason
        ),
        items=items[:21],
        truncated_by=lexical.truncated_by,
        searched_channels=("lexical", "semantic"),
        semantic_status=semantic_status,
        index_complete=index_complete,
        timed_out=timed_out,
    )


def load_raw_items_from_candidates(
    database_path: Path,
    batch: RawCandidateBatch,
    *,
    source_ids: frozenset[str] | None,
    deadline: float,
    character_budget: int = 6000,
) -> tuple[RawContextItem, ...]:
    """Release authorized Evidence bodies for semantic IDs. Not a vector dump."""
    ids = tuple(dict.fromkeys(hit.chunk.evidence_id for hit in batch.hits))
    if not ids or source_ids == frozenset():
        return ()
    readable, authority = _readable(source_ids)
    body_limit = min(20000, max(1, character_budget))
    items: list[RawContextItem] = []
    try:
        with _connection(database_path, deadline) as db:
            for evidence_id in ids[:21]:
                _check(deadline)
                row = _execute(
                    db,
                    deadline,
                    f"""
                    SELECT {_METADATA}, substr(e.verbatim,1,?) AS text,
                           length(e.verbatim)>? AS body_truncated
                    FROM evidence e
                    WHERE {readable} AND e.evidence_id=?
                    """,
                    [body_limit, body_limit, *authority, evidence_id],
                ).fetchone()
                if row is None:
                    continue
                try:
                    message = _message(row)
                    items.append(
                        RawContextItem(
                            source_id=row["source_id"],
                            conversation_id=row["conversation_id"],
                            anchor_evidence_id=message.evidence_id,
                            messages=(message,),
                            truncated=message.truncated,
                        )
                    )
                except (ValidationError, ValueError, TypeError):
                    continue
    except TimeoutError:
        raise
    except (sqlite3.Error, OSError):
        return ()
    return tuple(items)


def read_raw_indexed_context(
    database_path: Path,
    request: ContextSearchRequest,
    *,
    source_ids: frozenset[str] | None,
    deadline: float,
    index: RawIndexLookup | None = None,
    load_semantic_items: Callable[..., tuple[RawContextItem, ...]] | None = None,
) -> ContextLaneResult:
    lexical = read_raw_context(database_path, request, source_ids=source_ids, deadline=deadline)
    if index is None:
        return lexical
    try:
        batch, unpublished = index.lookup_raw(
            request.query, source_ids=source_ids, deadline=deadline
        )
    except Exception:
        batch, unpublished = RawCandidateBatch(reason="index_unavailable"), True
    extra: tuple[RawContextItem, ...] = ()
    if batch.hits:
        extra = (
            load_semantic_items(database_path, batch, source_ids=source_ids, deadline=deadline)
            if load_semantic_items is not None
            else load_raw_items_from_candidates(
                database_path,
                batch,
                source_ids=source_ids,
                deadline=deadline,
                character_budget=request.character_budget,
            )
        )
    return fuse_raw_lane(lexical, batch, unpublished_authorized=unpublished, extra_items=extra)
