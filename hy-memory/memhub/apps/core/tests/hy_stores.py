"""The pinned SDK's own Chroma and Kuzu stores, over a collection and connection a test controls.

Deletion is read back from these stores one level below the SDK's methods, and
only for these classes, so a fake client has to carry them rather than stand-ins.
"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any


def chroma_store(get: Callable[..., dict[str, Any]]) -> Any:
    from hy_memory.data.vector_store_chroma import ChromaVectorStore

    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._collection = SimpleNamespace(get=get)
    return store


def kuzu_store(execute: Callable[..., Any], *, available: bool = True) -> Any:
    from hy_memory.data.graph_store_kuzu import KuzuGraphStore

    store = KuzuGraphStore.__new__(KuzuGraphStore)
    store._conn = SimpleNamespace(execute=execute)
    store._available = available
    return store
