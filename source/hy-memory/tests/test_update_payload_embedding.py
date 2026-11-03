# -*- coding: utf-8 -*-
"""
update_payload 同时更新 embedding 的后端验证（chroma / qdrant / faiss）。

UPDATE 改为原地更新后，update_payload(node_id, {"content":..., "embedding": new_vec})
必须真正把库里的向量也换掉。本测试对每个后端：
  1. upsert 一个向量为 v_old 的节点；
  2. update_payload 把 embedding 换成 v_new（与 v_old 近正交）；
  3. 用 v_new 查询 → 该节点 cosine≈1 命中；用 v_old 查询 → 不再高分；
  4. get_embeddings 取回的向量 == v_new。
"""

import asyncio
import uuid

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _unit(vec):
    n = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / n for x in vec]


# 32 维：v_old 指向轴0，v_new 指向轴1（正交）
def _v_old():
    return _unit([1.0] + [0.0] * 31)


def _v_new():
    return _unit([0.0, 1.0] + [0.0] * 30)


def _mk_node(emb):
    n = MemoryNode(
        node_id="n1", user_id="u1", agent_id="a1", session_id="s1",
        content="原始内容", layer=MemoryLayer.L2_FACT,
        status=MemoryStatus.ACTIVE, is_latest=True,
    )
    n.embedding = emb
    return n


def _check_update_with_embedding(store):
    """通用断言：update_payload 带 embedding 后，向量确实被替换。"""
    run(store.upsert(_mk_node(_v_old())))

    # 原地更新：换内容 + 换向量
    ok = run(store.update_payload("n1", {
        "content": "更新后的内容",
        "embedding": _v_new(),
    }))
    assert ok is True

    # 1) get_embeddings 取回的应是 v_new
    embs = run(store.get_embeddings(["n1"]))
    assert "n1" in embs
    got = embs["n1"]
    # 与 v_new 点积≈1，与 v_old 点积≈0
    dot_new = sum(a * b for a, b in zip(got, _v_new()))
    dot_old = sum(a * b for a, b in zip(got, _v_old()))
    assert dot_new > 0.99, f"stored vector should match v_new, dot={dot_new}"
    assert abs(dot_old) < 0.01, f"stored vector should NOT match v_old, dot={dot_old}"

    # 2) 用 v_new 查询应命中 n1（高分）
    hits_new = run(store.search(query_embedding=_v_new(), user_id="u1", limit=5))
    ids_new = {h["node_id"]: h["score"] for h in hits_new}
    assert "n1" in ids_new
    assert ids_new["n1"] > 0.99

    # 3) content 也更新了
    node = run(store.get_by_id("n1"))
    assert node.content == "更新后的内容"


class TestChromaUpdateEmbedding:
    def test_update_payload_with_embedding(self, tmp_path):
        from hy_memory.data.vector_store_chroma import ChromaVectorStore
        cfg = MemoryConfig.from_dict({"vector_store": {
            "provider": "chroma",
            "collection_name": f"t_upd_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma"),
            "embedding_dims": 32,
        }})
        vs = ChromaVectorStore(cfg)
        run(vs.initialize())
        try:
            _check_update_with_embedding(vs)
        finally:
            run(vs.close())


def _qdrant_ok():
    try:
        import qdrant_client  # noqa
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _qdrant_ok(), reason="qdrant-client not installed")
class TestQdrantUpdateEmbedding:
    def test_update_payload_with_embedding(self, tmp_path):
        from hy_memory.data.vector_store_qdrant import QdrantVectorStore
        cfg = MemoryConfig.from_dict({"vector_store": {
            "provider": "qdrant",
            "collection_name": f"t_upd_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "qdrant"),
            "embedding_dims": 32,
        }})
        vs = QdrantVectorStore(cfg)
        run(vs.initialize())
        try:
            _check_update_with_embedding(vs)
        finally:
            run(vs.close())


def _faiss_ok():
    try:
        import faiss  # noqa
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _faiss_ok(), reason="faiss not installed")
class TestFaissUpdateEmbedding:
    def test_update_payload_with_embedding(self, tmp_path):
        from hy_memory.data.vector_store_faiss import FaissVectorStore
        cfg = MemoryConfig.from_dict({"vector_store": {
            "provider": "faiss",
            "collection_name": f"t_upd_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "faiss"),
            "embedding_dims": 32,
        }})
        vs = FaissVectorStore(cfg)
        run(vs.initialize())
        try:
            _check_update_with_embedding(vs)
        finally:
            run(vs.close())
