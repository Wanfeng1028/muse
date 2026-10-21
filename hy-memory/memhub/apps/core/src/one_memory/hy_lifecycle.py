"""Which memories HY no longer counts as current, read from HY itself.

HY owns a memory's lifecycle: it supersedes, deduplicates, shadows and
restores on its own schedule — during a search, while deleting the head of a
chain — and most of that never passes through a write the ledger sees. So
the ledger does not keep a copy of any of it; readers ask HY, once per read,
for the nodes it has set aside.

Only the vector store is read. HY writes a node's status there on every
transition, and the graph holds no status the vector store lacks.
"""

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from importlib import import_module
from types import MappingProxyType
from typing import Any

#: HY's one status for a node that is current. Everything else it writes —
#: superseded, shadow, archived, negated, conflicted — takes it out of recall.
_ACTIVE = "active"
#: HY's verbatim chunks. Stored as shadow from the start and never a memory,
#: so never something a reader could have shown.
_RAW_LAYER = "l1_raw"


class HyLifecycleUnreadable(RuntimeError):
    """HY's store could not be read; never to be taken for "nothing is hidden"."""


@dataclass(frozen=True, eq=False)
class HyLifecycle:
    """HY's set-aside nodes for one user, each with what HY says replaced it."""

    hidden: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "hidden", MappingProxyType(dict(self.hidden)))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, HyLifecycle) and dict(self.hidden) == dict(other.hidden)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.hidden.items())))

    def replaced_by(self, memory_id: str) -> tuple[str, ...]:
        return self.hidden.get(memory_id, ())

    def replacing(self, memory_id: str) -> tuple[str, ...]:
        """The set-aside memories HY names this one as the replacement of."""
        return tuple(sorted(old for old, by in self.hidden.items() if memory_id in by))


def read_hy_lifecycle(
    client: object, user_id: str, ids: Collection[str] | None = None
) -> HyLifecycle:
    """Every node of `user_id` HY holds as anything but active, in one read.

    With `ids`, only those nodes are looked up — what a single-memory read
    needs, and a lookup by key rather than a scan; `replacing` is then only
    known among them.

    Read one level below HY's own listing, which drops a failed read and
    answers empty: a hidden memory would then read as current.
    """
    native: Any = client
    try:
        chroma = import_module("hy_memory.data.vector_store_chroma")
        store = native._vector_store
        collection = store._collection
        if not isinstance(store, chroma.ChromaVectorStore) or collection is None:
            raise HyLifecycleUnreadable("hy_lifecycle_store_unsupported")
        found = collection.get(
            ids=None if ids is None else list(ids),
            where={
                "$and": [
                    {"user_id": {"$eq": user_id}},
                    {"status": {"$ne": _ACTIVE}},
                    {"layer": {"$ne": _RAW_LAYER}},
                ]
            },
            include=["metadatas"],
        )
        metadatas = found["metadatas"]
        point_ids = found["ids"]
        if (
            not isinstance(point_ids, list)
            or not isinstance(metadatas, list)
            or len(point_ids) != len(metadatas)
        ):
            raise HyLifecycleUnreadable("hy_lifecycle_store_mismatch")
    except HyLifecycleUnreadable:
        raise
    except Exception as error:
        raise HyLifecycleUnreadable("hy_lifecycle_unreadable") from error
    hidden: dict[str, tuple[str, ...]] = {}
    for point_id, metadata in zip(point_ids, metadatas, strict=True):
        if not isinstance(point_id, str) or not point_id or not isinstance(metadata, Mapping):
            raise HyLifecycleUnreadable("hy_lifecycle_store_mismatch")
        payload = chroma.ChromaVectorStore._chroma_metadata_to_payload(dict(metadata))
        node_id = payload.get("node_id") or point_id
        if not isinstance(node_id, str) or not node_id or node_id != point_id:
            raise HyLifecycleUnreadable("hy_lifecycle_store_mismatch")
        hidden[node_id] = _replacements(payload)
    return HyLifecycle(hidden=hidden)


def _replacements(payload: Mapping[str, object]) -> tuple[str, ...]:
    """What HY names as taking this node's place: its chain successor or the kept duplicate."""
    names: list[str] = []
    superseded_by = payload.get("superseded_by")
    if isinstance(superseded_by, list):
        names.extend(value for value in superseded_by if isinstance(value, str) and value)
    kept = payload.get("dedup_kept_id")
    custom = payload.get("custom")
    if isinstance(custom, str):
        try:
            custom = json.loads(custom)
        except ValueError:
            custom = None
    if not isinstance(kept, str) and isinstance(custom, Mapping):
        audit = custom.get("hy_dedup")
        if isinstance(audit, Mapping):
            kept = audit.get("kept_id")
    if isinstance(kept, str) and kept:
        names.append(kept)
    return tuple(dict.fromkeys(names))
