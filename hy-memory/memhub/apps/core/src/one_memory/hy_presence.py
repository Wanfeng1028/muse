"""Whether HY still holds a memory, read so that a failed read is never taken for an absence.

The pinned HY SDK turns read failures into "not found" at every level a
caller would normally use: `get` drops a failed graph query, Chroma's
`get_by_id` drops any error, and Kuzu's `get_node` answers None while the
graph is unavailable. A deletion confirmed through them can be confirmed by a
store that was never read. So each store is asked here one level lower, where
a failure still raises, without changing the SDK.
"""

from enum import StrEnum
from importlib import import_module
from typing import Any


class HyPresence(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


def confirm_deleted(client: object, memory_id: str) -> HyPresence:
    """PRESENT if either store still has it; ABSENT only if both were read and have none."""
    native: Any = client
    answers = (_in_vectors(native, memory_id), _in_graph(native, memory_id))
    if HyPresence.PRESENT in answers:
        return HyPresence.PRESENT
    if HyPresence.UNKNOWN in answers:
        return HyPresence.UNKNOWN
    return HyPresence.ABSENT


def _in_vectors(native: Any, memory_id: str) -> HyPresence:
    chroma = import_module("hy_memory.data.vector_store_chroma")
    store = native._vector_store
    if not isinstance(store, chroma.ChromaVectorStore) or store._collection is None:
        return HyPresence.UNKNOWN
    point_id = store._node_id_to_point_id(memory_id)

    async def read() -> Any:
        return await chroma._run_in_vdb_pool(store._collection.get, ids=[point_id], include=[])

    try:
        found = native._loop_thread.run(read())
    except Exception:
        return HyPresence.UNKNOWN
    return HyPresence.PRESENT if found["ids"] else HyPresence.ABSENT


def _in_graph(native: Any, memory_id: str) -> HyPresence:
    store = native._graph_store
    if store is None:
        # HY was set up without a graph: there is nowhere else for it to hold one.
        return HyPresence.ABSENT
    kuzu = import_module("hy_memory.data.graph_store_kuzu")
    if not isinstance(store, kuzu.KuzuGraphStore) or not store._available or store._conn is None:
        return HyPresence.UNKNOWN

    def count() -> int:
        result = store._conn.execute(
            "MATCH (m:Memory {node_id: $nid}) RETURN count(m);", {"nid": memory_id}
        )
        return int(result.get_next()[0])

    async def read() -> int:
        return int(await kuzu._run_in_kuzu_pool(count))

    try:
        held = native._loop_thread.run(read())
    except Exception:
        return HyPresence.UNKNOWN
    return HyPresence.PRESENT if held else HyPresence.ABSENT
