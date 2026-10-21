"""Independent raw-vector adapter. Eligibility is supplied by Core's SQLite snapshot.

No HY collection, document text, embedding function, migration/repair or authority
store lives here. Chroma PersistentClient is NOT physically read-only: even the
existing-collection handle can maintain backend metadata/index files. A caller
requiring filesystem read-only operation must not use this backend.

Scoring is an exact pass over the eligible vectors, not a global ANN top-K that
is filtered afterwards. Chroma's filtered query does not score every candidate
in its `where $in` allowlist: at 10k stored chunks an explicit 64-ID allowlist
returned 26 of 64 while reporting the query as complete, and 0 of 64 after the
writer handle was reopened. A post-filtered global search would be neither
permission-correct nor recall-correct, so the eligible embeddings are read
back and ranked here.
"""

from __future__ import annotations

import math
import re
import sqlite3
import struct
import threading
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from numbers import Real
from pathlib import Path
from time import monotonic
from typing import Any, Literal

ALLOWLIST_BATCH_SIZE = 2048


class VectorStoreError(RuntimeError):
    """Bounded failure code; callers must not treat corruption as complete empty search."""


@dataclass(frozen=True)
class RawVectorRecord:
    chunk_id: str
    build_id: str
    generation_id: str
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", tuple(self.vector))


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    build_id: str
    generation_id: str
    distance: float


@dataclass(frozen=True)
class VectorSearchResult:
    hits: tuple[VectorHit, ...]
    complete: bool
    eligible_count: int
    searched_count: int
    reason: Literal["deadline"] | None


class RawVectorStore:
    """Unopened constructor has no I/O. Use create/open_existing explicitly.

    Directory must be a dedicated, trusted Runtime retrieval-vectors directory,
    never the HY data directory. Only create/open_writer_existing enable upsert.
    Core must serialize writers across handles/processes; this instance's lock
    is not a persistent writer lease. close() releases only this Chroma client,
    retaining other live clients' references.
    """

    def __init__(
        self,
        directory: Path,
        *,
        generation_id: str,
        dimensions: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        _identifier(generation_id)
        if type(dimensions) is not int or not 1 <= dimensions <= 65536:
            raise VectorStoreError("vector_invalid_dimensions")
        self.directory = Path(directory)
        self.generation_id = generation_id
        self.dimensions = dimensions
        self.collection_name = "raw_" + sha256(generation_id.encode()).hexdigest()
        self._clock = clock
        self._client: Any = None
        self._collection: Any = None
        self._writable = False
        self._closed = False
        self._lock = threading.RLock()

    @classmethod
    def create(cls, directory: Path, *, generation_id: str, dimensions: int) -> RawVectorStore:
        """Explicit writer initialization. Refuses to reuse an existing collection."""
        value = cls(directory, generation_id=generation_id, dimensions=dimensions)
        value._open(create=True)
        return value

    @classmethod
    def open_existing(
        cls,
        directory: Path,
        *,
        generation_id: str,
        dimensions: int,
    ) -> RawVectorStore:
        """No logical index writes; persistent Chroma may still write maintenance files."""
        value = cls(directory, generation_id=generation_id, dimensions=dimensions)
        value._open(create=False)
        return value

    @classmethod
    def open_writer_existing(
        cls,
        directory: Path,
        *,
        generation_id: str,
        dimensions: int,
    ) -> RawVectorStore:
        """Explicit worker recovery; verifies existing collection, never creates/repairs."""
        value = cls(directory, generation_id=generation_id, dimensions=dimensions)
        value._open(create=False, writable=True)
        return value

    def _metadata(self) -> dict[str, str | int]:
        return {
            "adapter": "one-memory-raw-v1",
            "generation_id": self.generation_id,
            "dimensions": self.dimensions,
            "distance": "cosine",
            "normalization": "l2-float32-v1",
        }

    def _preflight(self, create: bool) -> None:
        if any(part.is_symlink() for part in (self.directory, *self.directory.parents)):
            raise VectorStoreError("vector_unsafe_directory")
        if not self.directory.exists():
            if not create:
                raise VectorStoreError("vector_store_not_found")
            self.directory.mkdir(parents=True)
        if not self.directory.is_dir():
            raise VectorStoreError("vector_unsafe_directory")
        database = self.directory / "chroma.sqlite3"
        if database.is_symlink():
            raise VectorStoreError("vector_unsafe_database")
        if not database.is_file():
            if not create:
                raise VectorStoreError("vector_store_not_found")
            if any(self.directory.iterdir()):
                raise VectorStoreError("vector_unknown_directory")
            return
        if database.stat().st_nlink != 1:
            raise VectorStoreError("vector_unsafe_database")
        # Refuse missing/corrupt collections BEFORE PersistentClient can perform
        # startup maintenance. This checks the installed Chroma 1.5.9 schema.
        try:
            with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                found = db.execute(
                    "SELECT 1 FROM collections WHERE name=?", (self.collection_name,)
                ).fetchone()
                if not create and found is None:
                    raise VectorStoreError("vector_collection_not_found")
                if create and found is not None:
                    raise VectorStoreError("vector_collection_exists")
        except sqlite3.Error:
            raise VectorStoreError("vector_store_unavailable") from None

    def _open(self, *, create: bool, writable: bool = False) -> None:
        self._preflight(create)
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=str(self.directory), settings=Settings(anonymized_telemetry=False)
            )
            if create:
                self._collection = self._client.create_collection(
                    self.collection_name,
                    embedding_function=None,
                    metadata=self._metadata(),
                    # Unit vectors + inner product give cosine distance without
                    # cosine HNSW's lossy normalization/de-normalization on get.
                    configuration={"hnsw": {"space": "ip"}},
                )
            else:
                self._collection = self._client.get_collection(
                    self.collection_name, embedding_function=None
                )
            if (
                self._collection.metadata != self._metadata()
                or type(self._collection.metadata.get("dimensions")) is not int
            ):
                raise VectorStoreError("vector_collection_identity_mismatch")
            config = self._collection.configuration
            if (
                config.get("hnsw", {}).get("space") != "ip"
                or config.get("embedding_function") is not None
            ):
                raise VectorStoreError("vector_collection_configuration_mismatch")
            self._writable = create or writable
        except Exception as error:
            self.close()
            if isinstance(error, VectorStoreError):
                raise
            raise VectorStoreError("vector_store_unavailable") from None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._client is not None:
                self._client.close()
            self._client = self._collection = None

    def _require_open(self) -> Any:
        if self._closed:
            raise VectorStoreError("vector_store_closed")
        if self._collection is None:
            raise VectorStoreError("vector_store_not_open")
        return self._collection

    def _records(self, records: Sequence[RawVectorRecord]) -> tuple[RawVectorRecord, ...]:
        result = []
        seen: set[str] = set()
        for record in records:
            if not isinstance(record, RawVectorRecord):
                raise VectorStoreError("vector_invalid_record")
            for identifier in (record.chunk_id, record.build_id, record.generation_id):
                _identifier(identifier)
            if record.generation_id != self.generation_id or record.chunk_id in seen:
                raise VectorStoreError("vector_invalid_record_identity")
            seen.add(record.chunk_id)
            result.append(
                RawVectorRecord(
                    record.chunk_id,
                    record.build_id,
                    record.generation_id,
                    _vector(record.vector, self.dimensions),
                )
            )
        return tuple(result)

    def _read_records(self, ids: Sequence[str]) -> dict[str, tuple[RawVectorRecord, str]]:
        if not ids:
            return {}
        collection = self._require_open()
        result: dict[str, tuple[RawVectorRecord, str]] = {}
        for start in range(0, len(ids), ALLOWLIST_BATCH_SIZE):
            batch = ids[start : start + ALLOWLIST_BATCH_SIZE]
            try:
                data = collection.get(ids=list(batch), include=["embeddings", "metadatas"])
                returned, vectors, metadatas = data["ids"], data["embeddings"], data["metadatas"]
                if (
                    vectors is None
                    or metadatas is None
                    or not len(returned) == len(vectors) == len(metadatas)
                ):
                    raise VectorStoreError("vector_invalid_record_response")
                for key, vector, metadata in zip(returned, vectors, metadatas, strict=True):
                    if key not in batch or key in result:
                        raise VectorStoreError("vector_ineligible_record")
                    result[key] = self._decode(key, vector, metadata)
            except VectorStoreError:
                raise
            except Exception:
                raise VectorStoreError("vector_read_unavailable") from None
        return result

    def _decode(
        self, key: str, vector: Sequence[float], metadata: Any
    ) -> tuple[RawVectorRecord, str]:
        if not isinstance(metadata, dict) or set(metadata) != {
            "chunk_id",
            "build_id",
            "generation_id",
            "vector_sha256",
            "input_sha256",
        }:
            raise VectorStoreError("vector_invalid_metadata")
        if metadata["chunk_id"] != key or metadata["generation_id"] != self.generation_id:
            raise VectorStoreError("vector_metadata_identity_mismatch")
        _identifier(key)
        _identifier(metadata["build_id"])
        if not isinstance(metadata["input_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", metadata["input_sha256"]
        ):
            raise VectorStoreError("vector_invalid_input_digest")
        normalized = _vector(vector, self.dimensions)
        if metadata["vector_sha256"] != _digest(normalized):
            raise VectorStoreError("vector_content_mismatch")
        return RawVectorRecord(key, metadata["build_id"], self.generation_id, normalized), metadata[
            "input_sha256"
        ]

    def upsert(self, records: Sequence[RawVectorRecord]) -> None:
        """Idempotent immutable insertion; add-only at Chroma, never overwrite IDs.

        Equality is canonical float32 input identity plus explicit normalized
        storage identity. Conflict is checked before
        any add. Backend failure may leave a partial new batch: caller must verify
        the entire build before publication. Existing IDs are never modified.
        """
        with self._lock:
            collection = self._require_open()
            if not self._writable:
                raise VectorStoreError("vector_store_read_only")
            incoming = self._records(records)
            existing = self._read_records([record.chunk_id for record in incoming])
            for record in incoming:
                if record.chunk_id in existing and not _matches(existing[record.chunk_id], record):
                    raise VectorStoreError("vector_immutable_conflict")
            new = [record for record in incoming if record.chunk_id not in existing]
            for start in range(0, len(new), ALLOWLIST_BATCH_SIZE):
                batch = new[start : start + ALLOWLIST_BATCH_SIZE]
                try:
                    collection.add(
                        ids=[record.chunk_id for record in batch],
                        embeddings=[list(_unit_vector(record.vector)) for record in batch],
                        metadatas=[
                            {
                                "chunk_id": record.chunk_id,
                                "build_id": record.build_id,
                                "generation_id": record.generation_id,
                                "vector_sha256": _digest(_unit_vector(record.vector)),
                                "input_sha256": _digest(record.vector),
                            }
                            for record in batch
                        ],
                    )
                except Exception:
                    raise VectorStoreError("vector_write_unavailable") from None
            self.verify(incoming)

    def verify(self, records: Sequence[RawVectorRecord]) -> None:
        """Verify every expected ID, metadata, dimensions and exact float32 vector."""
        with self._lock:
            self._require_open()
            expected = self._records(records)
            actual = self._read_records([record.chunk_id for record in expected])
            for record in expected:
                if record.chunk_id not in actual:
                    raise VectorStoreError("vector_record_missing")
                if not _matches(actual[record.chunk_id], record):
                    raise VectorStoreError("vector_immutable_conflict")

    def verify_candidates(
        self,
        candidates: Sequence[tuple[str, str]],
        *,
        deadline: float,
    ) -> bool:
        """Read-only presence/integrity check for (chunk_id, expected_build_id).

        Costs O(candidates * dimensions), not a bounded top-K lookup. False means
        deadline exhaustion, never proof of absence. Each read covers at most
        2048 IDs; synchronous backend calls cannot be interrupted. This is not a
        snapshot across Chroma and SQLite: Core still owns final eligibility
        checks and writer serialization. Chroma may perform maintenance writes.
        """
        with self._lock:
            self._require_open()
            if (
                isinstance(deadline, bool)
                or not isinstance(deadline, Real)
                or not math.isfinite(deadline)
            ):
                raise VectorStoreError("vector_invalid_deadline")
            if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
                raise VectorStoreError("vector_invalid_candidates")
            expected: list[tuple[str, str]] = []
            seen: set[str] = set()
            for pair in candidates:
                if (
                    not isinstance(pair, Sequence)
                    or isinstance(pair, (str, bytes))
                    or len(pair) != 2
                ):
                    raise VectorStoreError("vector_invalid_candidates")
                key, build = pair
                _identifier(key)
                _identifier(build)
                if key in seen:
                    raise VectorStoreError("vector_duplicate_candidates")
                seen.add(key)
                expected.append((key, build))
            for start in range(0, len(expected), ALLOWLIST_BATCH_SIZE):
                if self._clock() >= deadline:
                    return False
                batch = expected[start : start + ALLOWLIST_BATCH_SIZE]
                # Bound this call to one batch so it cannot read past the next
                # deadline checkpoint via _read_records' internal loop.
                actual = self._read_records([key for key, _build in batch])
                for key, build in batch:
                    if key not in actual:
                        raise VectorStoreError("vector_record_missing")
                    if actual[key][0].build_id != build:
                        raise VectorStoreError("vector_metadata_identity_mismatch")
                if self._clock() >= deadline:
                    return False
            return True

    def search(
        self,
        query_vector: Sequence[float],
        eligible_ids: Sequence[str],
        limit: int,
        deadline: float,
    ) -> VectorSearchResult:
        """Rank exactly the eligible candidates; synchronous backend cannot be preempted.

        deadline is absolute monotonic seconds. A late batch is discarded; prior
        on-time batches may return partial. complete means every eligible
        vector was scored, NOT complete index coverage: only chunks the caller
        already resolved as eligible and published are searched.

        The eligible embeddings are read back in bounded batches and ranked
        here, because Chroma's own filtered query does not score every ID in
        its allowlist. A global top-K filtered afterwards would rank
        unauthorized vectors first and let them crowd the eligible ones out.
        """
        with self._lock:
            self._require_open()
            vector = _unit_vector(_vector(query_vector, self.dimensions))
            if type(limit) is not int or not 1 <= limit <= ALLOWLIST_BATCH_SIZE:
                raise VectorStoreError("vector_invalid_limit")
            if (
                isinstance(deadline, bool)
                or not isinstance(deadline, Real)
                or not math.isfinite(deadline)
            ):
                raise VectorStoreError("vector_invalid_deadline")
            if isinstance(eligible_ids, (str, bytes)):
                raise VectorStoreError("vector_invalid_allowlist")
            ids = tuple(eligible_ids)
            for key in ids:
                _identifier(key)
            if len(set(ids)) != len(ids):
                raise VectorStoreError("vector_duplicate_allowlist")
            hits: list[VectorHit] = []
            searched = 0
            for start in range(0, len(ids), ALLOWLIST_BATCH_SIZE):
                if self._clock() >= deadline:
                    break
                batch = ids[start : start + ALLOWLIST_BATCH_SIZE]
                try:
                    read = self._read_records(batch)
                except VectorStoreError as error:
                    # A missing or corrupt eligible vector is not "no hits".
                    raise VectorStoreError("vector_query_unavailable") from error
                if self._clock() >= deadline:
                    break
                try:
                    missing = [key for key in batch if key not in read]
                    if missing:
                        # The caller resolved these as eligible and published,
                        # so an absent vector is a broken build, not a miss.
                        raise VectorStoreError("vector_query_unavailable")
                    validated = [
                        VectorHit(
                            key,
                            read[key][0].build_id,
                            read[key][0].generation_id,
                            # Stored vectors are unit length, so the inner
                            # product is the cosine similarity.
                            1.0 - _dot(read[key][0].vector, vector),
                        )
                        for key in batch
                    ]
                except VectorStoreError:
                    raise
                except Exception:
                    raise VectorStoreError("vector_invalid_query_response") from None
                if self._clock() >= deadline:
                    break
                searched += len(batch)
                hits.extend(validated)
                hits.sort(key=lambda hit: (hit.distance, hit.chunk_id))
                del hits[limit:]
            complete = searched == len(ids)
            return VectorSearchResult(
                tuple(hits), complete, len(ids), searched, None if complete else "deadline"
            )


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def _identifier(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,255}", value):
        raise VectorStoreError("vector_invalid_identifier")


def _vector(value: Sequence[float], dimensions: int) -> tuple[float, ...]:
    try:
        if len(value) != dimensions or any(
            isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in value
        ):
            raise VectorStoreError("vector_invalid_values_or_dimensions")
        packed = struct.pack(f"<{dimensions}f", *value)
        normalized = struct.unpack(f"<{dimensions}f", packed)
        if not all(math.isfinite(v) for v in normalized) or not any(normalized):
            raise VectorStoreError("vector_invalid_values_or_dimensions")
        return normalized
    except VectorStoreError:
        raise
    except (ValueError, TypeError, OverflowError, struct.error):
        raise VectorStoreError("vector_invalid_values_or_dimensions") from None


def _digest(vector: tuple[float, ...]) -> str:
    return sha256(struct.pack(f"<{len(vector)}f", *vector)).hexdigest()


def _unit_vector(vector: tuple[float, ...]) -> tuple[float, ...]:
    length = math.sqrt(math.fsum(component * component for component in vector))
    return _vector(tuple(component / length for component in vector), len(vector))


def _matches(actual: tuple[RawVectorRecord, str], expected: RawVectorRecord) -> bool:
    stored, input_digest = actual
    return input_digest == _digest(expected.vector) and stored == RawVectorRecord(
        expected.chunk_id, expected.build_id, expected.generation_id, _unit_vector(expected.vector)
    )
