"""Internal raw semantic candidate lookup. No route, raw body release or full coverage claim."""

import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from one_memory.context_raw import _check
from one_memory.retrieval.index_store import PublishedChunk, RetrievalIndexStore
from one_memory.retrieval.models import RetrievalPath, TimeRange
from one_memory.retrieval.vector_store import RawVectorStore, VectorStoreError


@dataclass(frozen=True)
class RawSemanticCandidate:
    chunk: PublishedChunk
    distance: float


@dataclass(frozen=True)
class RawCandidateBatch:
    hits: tuple[RawSemanticCandidate, ...] = ()
    complete: bool = False
    reason: str | None = None
    coverage: Literal["indexed_only"] = "indexed_only"
    time_range: TimeRange | None = None


def read_raw_semantic_candidates(
    store: RetrievalIndexStore,
    vectors: RawVectorStore,
    query_vector: Sequence[float],
    *,
    generation_id: str,
    source_ids: frozenset[str],
    deadline: float,
    limit: int = 64,
    time_range: TimeRange | None = None,
) -> RawCandidateBatch:
    """Caller resolves host authority; explicit source IDs can only narrow it.

    complete means the eligible published chunks were checked and searched, not
    that every authorized original is indexed. The future coordinator must still
    revalidate host identity and all raw/memory data together before body release.
    """
    if not isinstance(source_ids, frozenset) or any(
        not isinstance(source, str) or not 1 <= len(source) <= 128 for source in source_ids
    ):
        raise ValueError("explicit_resolved_sources_required")
    if type(limit) is not int or not 1 <= limit <= 64:
        raise ValueError("invalid_candidate_limit")
    if isinstance(deadline, bool) or not math.isfinite(deadline):
        raise ValueError("invalid_candidate_deadline")
    if not source_ids:
        return RawCandidateBatch(reason="not_authorized")
    if vectors.generation_id != generation_id:
        raise ValueError("candidate_generation_mismatch")
    try:
        _check(deadline)
        eligible = store.active_chunks(
            generation_id, source_ids=source_ids, time_range=time_range, deadline=deadline
        )
        if not eligible:
            return RawCandidateBatch(
                complete=True, reason="no_eligible_chunks", time_range=time_range
            )
        before = {chunk.chunk_id: chunk for chunk in eligible}
        expected_vectors = [(chunk.chunk_id, chunk.build_id) for chunk in eligible]
        # When one query can return the entire allowlist, that response itself
        # is the integrity check. Avoid a duplicate Chroma get-before-query on
        # the hot small/medium-authority path. Larger allowlists still need the
        # explicit complete verification because search returns only top-K.
        verify_before_search = len(eligible) > limit
        if verify_before_search and not vectors.verify_candidates(
            expected_vectors, deadline=deadline
        ):
            return RawCandidateBatch(reason="deadline")
        result = vectors.search(query_vector, tuple(before), limit, deadline)
        if not verify_before_search and {hit.chunk_id for hit in result.hits} != set(before):
            raise VectorStoreError("vector_record_missing")
        _check(deadline)
        current = {
            chunk.chunk_id: chunk
            for chunk in store.active_chunks(
                generation_id, source_ids=source_ids, time_range=time_range, deadline=deadline
            )
        }
        hits = []
        for hit in result.hits:
            if (
                hit.chunk_id not in before
                or hit.generation_id != generation_id
                or hit.build_id != before[hit.chunk_id].build_id
            ):
                raise VectorStoreError("candidate_identity_mismatch")
            if current.get(hit.chunk_id) == before[hit.chunk_id]:
                hits.append(RawSemanticCandidate(before[hit.chunk_id], hit.distance))
        _check(deadline)
        unchanged = before == current
        return RawCandidateBatch(
            tuple(hits),
            result.complete and unchanged,
            "evidence_changed" if not unchanged else result.reason,
            time_range=time_range,
        )
    except TimeoutError:
        return RawCandidateBatch(reason="deadline")
    except VectorStoreError:
        return RawCandidateBatch(reason="vector_unavailable")
    except (sqlite3.Error, OSError, ValueError):
        return RawCandidateBatch(reason="index_unavailable")


def compose_raw_retrieval_path(
    batch: RawCandidateBatch,
    *,
    unpublished_authorized: bool,
    lexical_hit_count: int,
) -> RetrievalPath:
    """Map channel results to a path. Indexed-only search is never complete empty."""
    if type(lexical_hit_count) is not int or lexical_hit_count < 0:
        raise ValueError("invalid_lexical_hit_count")
    hits = len(batch.hits) + lexical_hit_count
    incomplete = unpublished_authorized or not batch.complete
    channels: tuple[Literal["lexical", "semantic"], ...] = ("lexical", "semantic")
    if hits:
        return RetrievalPath(
            status="ok",
            returned_count=min(hits, 32),
            searched_channels=channels,
            coverage="partial" if incomplete else "complete",
        )
    if incomplete:
        return RetrievalPath(
            status="degraded",
            reason="indexed_only",
            returned_count=0,
            searched_channels=channels,
            coverage="partial",
        )
    return RetrievalPath(
        status="empty",
        returned_count=0,
        searched_channels=channels,
        coverage="complete",
    )
