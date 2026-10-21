# -*- coding: utf-8 -*-
"""
clone_user 在 BM25 sparse qdrant 集合上的回归。

0.1.6.4 起 qdrant 启用 fastembed BM25 后，scroll/retrieve 返回的 point.vector
是命名多向量 dict（{"": dense, "bm25": SparseVector}）。clone 走 list_by_user
读 src 节点，旧代码把整个 dict 赋给 node.embedding；clone 复制后再 upsert，
_build_vector_field 把 dict 当 List[float] 又包一层 → 非法嵌套 → PointStruct
ValidationError → rollback → cloned_count=0。

本测试在带 sparse 的 qdrant 集合上：
  1. list_by_user 返回的 embedding 必须是 List[float]（不是 dict）；
  2. clone_user 成功，cloned_count == src 节点数；
  3. dst 可被 list_by_user 读回，数量一致。
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


def _emb(dims=32):
    import random
    v = [random.gauss(0, 1) for _ in range(dims)]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def _qdrant_sparse_ok():
    try:
        import qdrant_client  # noqa
        from hy_memory.pipelines._retrieval import bm25_fastembed
        return bm25_fastembed.is_available()
    except Exception:
        return False


def _mk(node_id, content, uid="src_u", aid="a1"):
    n = MemoryNode(
        node_id=node_id, user_id=uid, agent_id=aid, session_id="s1",
        content=content, layer=MemoryLayer.L2_FACT,
        status=MemoryStatus.ACTIVE, is_latest=True,
    )
    n.embedding = _emb()
    return n


@pytest.mark.skipif(not _qdrant_sparse_ok(),
                    reason="qdrant-client + fastembed (BM25 sparse) required")
class TestCloneQdrantSparse:
    def test_clone_on_bm25_sparse_collection(self, tmp_path):
        from hy_memory.data.vector_store_qdrant import QdrantVectorStore

        cfg = MemoryConfig.from_dict({"vector_store": {
            "provider": "qdrant",
            "collection_name": f"t_clone_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "qdrant"),
            "embedding_dims": 32,
        }})
        vs = QdrantVectorStore(cfg)
        run(vs.initialize())
        try:
            # 该集合应启用 BM25 sparse（否则测不到回归）
            assert vs._supports_fulltext, "expected BM25 sparse collection"

            src_uid = "src_user_clone"
            nodes = [_mk(f"n{i}", f"用户喜欢运动项目{i}", uid=src_uid) for i in range(5)]
            run(vs.upsert_batch(nodes))

            # 1) list_by_user 的 embedding 必须是 List[float]，不能是多向量 dict
            listed = run(vs.list_by_user(src_uid, agent_id="a1"))
            assert len(listed) == 5
            for nd in listed:
                assert isinstance(nd.embedding, list), \
                    f"embedding 应为 List[float]，实际 {type(nd.embedding)}"
                assert nd.embedding and not isinstance(nd.embedding[0], dict)

            # 2) 模拟 clone：复制 list_by_user 读到的节点到新 user 再 upsert
            #    （等价于 async_clone_user 的核心数据流，复现「读→复制→写」）
            cloned = []
            for nd in listed:
                c = MemoryNode(
                    node_id=str(uuid.uuid4()), user_id="dst_user_clone",
                    agent_id="a1", session_id="s1", content=nd.content,
                    layer=nd.layer, status=MemoryStatus.ACTIVE, is_latest=True,
                )
                c.embedding = nd.embedding  # 复制读路径的 embedding
                cloned.append(c)
            written = run(vs.upsert_batch(cloned))
            assert len(written) == 5, f"clone upsert 应写入 5 条，实际 {len(written)}"

            # 3) dst 可读回，数量一致
            dst = run(vs.list_by_user("dst_user_clone", agent_id="a1"))
            assert len(dst) == 5
        finally:
            run(vs.close())
