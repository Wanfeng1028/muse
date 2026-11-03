"""Bounded raw-index work. No migration, scheduler, HY or remote model invocation.

Runtime must admit a single worker, own its thread/process, and drain that owner
before closing the vector client. Cancellation here is cooperative between
native calls, not a claim that ONNX/Chroma can be preempted in a Python thread.
"""

import math
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from one_memory.embedding_assets import (
    BUILTIN_EMBEDDING_MODEL,
    EMBEDDING_ASSETS,
    verify_assets,
)
from one_memory.local_embedding import LocalEmbedder, TokenizedText
from one_memory.retrieval.chunking import ChunkingError, chunk_evidence
from one_memory.retrieval.content import index_content
from one_memory.retrieval.index_store import (
    EncoderIdentity,
    IndexLease,
    RetrievalIndexStore,
    chunk_identity,
)
from one_memory.retrieval.mapped_content import MappedContentError, chunk_mapped_content
from one_memory.retrieval.vector_store import RawVectorRecord, RawVectorStore, VectorStoreError


class RetrievalEncoder(Protocol):
    @property
    def identity(self) -> EncoderIdentity: ...

    def tokenize_with_offsets(self, text: str) -> TokenizedText: ...

    def encode_documents(self, texts: list[str]) -> list[list[float]]: ...


class LocalRetrievalEncoder:
    """Pinned local assets; mapped content v2 by default, explicit v1 for old generations."""

    def __init__(self, embedder: LocalEmbedder | None = None, *, content_version: int = 2):
        if type(content_version) is not int or content_version not in (1, 2):
            raise ValueError("unsupported_content_generation")
        self._embedder = embedder if embedder is not None else LocalEmbedder()
        digests = {asset.filename: asset.sha256 for asset in EMBEDDING_ASSETS}
        self.identity = EncoderIdentity(
            BUILTIN_EMBEDDING_MODEL,
            digests["model_int8.onnx"],
            digests["tokenizer.json"],
            self._embedder.dimensions,
            chunker_version=content_version,
            normalizer_version=content_version,
        )
        self._verified = False
        self._lock = threading.Lock()

    def _verify(self) -> None:
        with self._lock:
            if not self._verified:
                verify_assets()
                self._verified = True

    def tokenize_with_offsets(self, text: str) -> TokenizedText:
        self._verify()
        return self._embedder.tokenize_with_offsets(text)

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        self._verify()
        if len(texts) > 8 or any(
            not 1 <= len(self.tokenize_with_offsets(text).token_ids) <= 512 for text in texts
        ):
            raise ValueError("encoder_batch_or_token_budget")
        with self._lock:
            return self._embedder.encode(texts)


@dataclass(frozen=True)
class IndexWorkResult:
    state: Literal["idle", "ready", "excluded", "blocked", "cancelled", "deferred"]
    reason: str | None = None
    chunk_count: int = 0


class _Interrupted(Exception):
    def __init__(self, state: Literal["cancelled", "deferred"]):
        self.state = state


class RetrievalIndexWorker:
    def __init__(
        self,
        store: RetrievalIndexStore,
        vectors: RawVectorStore,
        encoder: RetrievalEncoder,
        *,
        generation_id: str,
        owner: str,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        max_job_seconds: float = 120,
    ):
        if (
            not owner
            or len(owner) > 128
            or isinstance(max_job_seconds, bool)
            or not math.isfinite(max_job_seconds)
            or not 0 < max_job_seconds <= 300
        ):
            raise ValueError("invalid_worker_budget")
        if store.encoder_identity(generation_id) != encoder.identity:
            raise ValueError("worker_encoder_identity_mismatch")
        if (
            vectors.generation_id != generation_id
            or vectors.dimensions != encoder.identity.dimensions
        ):
            raise ValueError("worker_vector_identity_mismatch")
        self.store, self.vectors, self.encoder = store, vectors, encoder
        self.generation_id, self.owner = generation_id, owner
        self.clock, self.wall_clock = clock, wall_clock
        self.max_job_seconds = max_job_seconds
        self._run_lock = threading.Lock()

    def run_once(self, *, cancel: threading.Event | None = None) -> IndexWorkResult:
        """Consume <=256 events and handle <=1 document; never activate a generation.

        Interrupted jobs retain their finite lease for restart recovery. Failed
        jobs are blocked for explicit retry; arbitrary provider exceptions and
        original text never enter the public result or a log.
        """
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("index_worker_already_running")
        lease: IndexLease | None = None
        deadline = self.clock() + self.max_job_seconds

        def check() -> None:
            if cancel is not None and cancel.is_set():
                raise _Interrupted("cancelled")
            now = self.clock()
            if not math.isfinite(now) or now >= deadline:
                raise _Interrupted("deferred")

        def boundary() -> None:
            nonlocal lease
            check()
            assert lease is not None
            # This revalidates the original's current fingerprint and authority,
            # not just a heartbeat on an otherwise stale claim.
            lease = self.store.renew(lease, now=self.wall_clock())
            check()

        def publish_checkpoint() -> None:
            check()
            assert lease is not None
            now = self.wall_clock()
            if not math.isfinite(now) or now >= lease.expires_at:
                raise ValueError("lease_changed_or_expired")

        try:
            check()
            self.store.consume_pending(self.generation_id)
            check()
            lease = self.store.claim(self.generation_id, self.owner, now=self.wall_clock())
            if lease is None:
                return IndexWorkResult("idle")
            record = self.store.read_lease(lease, now=self.wall_clock())
            check()
            identity = self.encoder.identity
            try:
                prepared = index_content(
                    record,
                    normalizer_version=identity.normalizer_version,
                    chunker_version=identity.chunker_version,
                )
            except ValueError:
                self.store.block(lease)
                return IndexWorkResult("blocked", "content_mapping_required")

            worker_encoder = self.encoder

            class CheckedTokenizer:
                def tokenize_with_offsets(self, text: str) -> TokenizedText:
                    check()
                    result = worker_encoder.tokenize_with_offsets(text)
                    check()
                    return result

            chunks = (
                chunk_mapped_content(prepared, CheckedTokenizer())
                if prepared is not None
                else chunk_evidence(record.verbatim, CheckedTokenizer())
            )
            if (not chunks and prepared is None) or len(chunks) > 8192:
                raise ChunkingError("invalid_chunk_count")
            source_map = prepared.metadata if prepared is not None else None
            map_digest = source_map.digest if source_map is not None else None
            boundary()
            expected: list[RawVectorRecord] = []
            for start in range(0, len(chunks), 8):
                batch = chunks[start : start + 8]
                boundary()
                encoded = self.encoder.encode_documents([chunk.text for chunk in batch])
                boundary()
                if len(encoded) != len(batch):
                    raise ValueError("encoder_count_mismatch")
                records = [
                    RawVectorRecord(
                        chunk_identity(lease, chunk, map_digest),
                        lease.build_id,
                        lease.generation_id,
                        tuple(vector),
                    )
                    for chunk, vector in zip(batch, encoded, strict=True)
                ]
                self.vectors.upsert(records)
                boundary()
                expected.extend(records)
            self._verify(expected, boundary)
            assert lease is not None
            check()
            self.store.publish(
                lease,
                chunks,
                vectors_verified=True,
                now=self.wall_clock(),
                source_map=source_map,
                checkpoint=publish_checkpoint,
            )
            return IndexWorkResult("ready" if chunks else "excluded", chunk_count=len(chunks))
        except _Interrupted as error:
            return IndexWorkResult(
                error.state, "cancelled" if error.state == "cancelled" else "deadline"
            )
        except Exception as error:
            cause: BaseException | None = error
            while cause is not None:
                if isinstance(cause, _Interrupted):
                    return IndexWorkResult(
                        cause.state, "cancelled" if cause.state == "cancelled" else "deadline"
                    )
                cause = cause.__cause__
            if lease is None:
                raise
            self.store.block(lease)
            reason = (
                "chunking_unavailable"
                if isinstance(error, (ChunkingError, MappedContentError))
                else "vector_unavailable"
                if isinstance(error, VectorStoreError)
                else "index_build_unavailable"
            )
            return IndexWorkResult("blocked", reason)
        finally:
            self._run_lock.release()

    def _verify(self, records: Sequence[RawVectorRecord], boundary: Callable[[], None]) -> None:
        for start in range(0, len(records), 8):
            self.vectors.verify(records[start : start + 8])
            boundary()
