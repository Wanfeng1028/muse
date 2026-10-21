# -*- coding: utf-8 -*-
"""
测试 delete_by_metadata — 验证按 metadata 字段组合删除的核心功能

覆盖:
- VectorStore (FAISS 纯内存, Chroma 嵌入式) 的 delete_by_metadata
- 四种删除粒度: user / user+agent / user+agent+session / 单条
- 验证删除后 search 确实找不到
- 边界: 空库删除、不存在的 user_id 等
- delete_by_isolation_key 回归（Chroma 之前 return -1）

运行方式:
    pytest tests/test_delete_by_metadata.py -v
"""

import asyncio
import uuid
from typing import List

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus


# ==================== 工具函数 ====================

def run(coro):
    """同步运行协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_node(
    user_id: str,
    agent_id: str = "agent_default",
    session_id: str = "sess_default",
    content: str = "test content",
    dims: int = 32,
) -> MemoryNode:
    """创建一个带 embedding 的 MemoryNode"""
    import random
    node = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id=user_id,
        agent_id=agent_id,
        session_id=session_id,
        content=content,
        layer=MemoryLayer.L2_FACT,
        status=MemoryStatus.ACTIVE,
    )
    # 随机 embedding, 归一化
    vec = [random.gauss(0, 1) for _ in range(dims)]
    norm = sum(v * v for v in vec) ** 0.5
    node.embedding = [v / norm for v in vec]
    return node


# ==================== FAISS 测试 ====================

class TestFaissDeleteByMetadata:
    """FAISS VectorStore 的 delete_by_metadata 测试"""

    DIMS = 32

    @pytest.fixture
    def store(self, tmp_path):
        """创建并初始化 FAISS VectorStore"""
        config = MemoryConfig.from_dict({
            "vector_store": {
                "provider": "faiss",
                "collection_name": "test_delete",
                "persist_directory": str(tmp_path / "faiss_data"),
                "embedding_dims": self.DIMS,
            },
        })
        from hy_memory.data.vector_store_faiss import FaissVectorStore
        vs = FaissVectorStore(config)
        run(vs.initialize())
        yield vs
        run(vs.close())

    def _insert_nodes(self, store, nodes: List[MemoryNode]):
        """批量插入节点"""
        run(store.upsert_batch(nodes))

    # --- 基本功能 ---

    def test_delete_by_user_id_only(self, store):
        """粒度1: 只传 user_id → 删除该用户所有记忆"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "a2", "s2", dims=self.DIMS)
        n3 = _make_node("u2", "a1", "s1", dims=self.DIMS)  # 不同用户
        self._insert_nodes(store, [n1, n2, n3])

        deleted = run(store.delete_by_metadata(user_id="u1"))
        assert deleted == 2

        # u1 的都没了
        assert run(store.get_by_id(n1.node_id)) is None
        assert run(store.get_by_id(n2.node_id)) is None
        # u2 的还在
        assert run(store.get_by_id(n3.node_id)) is not None

    def test_delete_by_user_and_agent(self, store):
        """粒度2: user_id + agent_id → 删除该用户指定 agent 下所有记忆"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "a1", "s2", dims=self.DIMS)
        n3 = _make_node("u1", "a2", "s1", dims=self.DIMS)  # 同用户不同 agent
        self._insert_nodes(store, [n1, n2, n3])

        deleted = run(store.delete_by_metadata(user_id="u1", agent_id="a1"))
        assert deleted == 2

        assert run(store.get_by_id(n1.node_id)) is None
        assert run(store.get_by_id(n2.node_id)) is None
        assert run(store.get_by_id(n3.node_id)) is not None

    def test_delete_by_user_agent_session(self, store):
        """粒度3: user_id + agent_id + session_id → 精确 session"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "a1", "s2", dims=self.DIMS)
        n3 = _make_node("u1", "a1", "s3", dims=self.DIMS)
        self._insert_nodes(store, [n1, n2, n3])

        deleted = run(store.delete_by_metadata(user_id="u1", agent_id="a1", session_id="s2"))
        assert deleted == 1

        assert run(store.get_by_id(n1.node_id)) is not None
        assert run(store.get_by_id(n2.node_id)) is None
        assert run(store.get_by_id(n3.node_id)) is not None

    # --- 边界情况 ---

    def test_delete_empty_store(self, store):
        """空库删除不报错，返回 0"""
        deleted = run(store.delete_by_metadata(user_id="nonexistent"))
        assert deleted == 0

    def test_delete_nonexistent_user(self, store):
        """删除不存在的用户，返回 0，不影响现有数据"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        self._insert_nodes(store, [n1])

        deleted = run(store.delete_by_metadata(user_id="u_not_exist"))
        assert deleted == 0
        assert run(store.get_by_id(n1.node_id)) is not None

    def test_delete_user_all_then_count_zero(self, store):
        """删除用户全部记忆后，该用户记忆数量为 0"""
        nodes = [_make_node("u1", f"a{i}", f"s{i}", dims=self.DIMS) for i in range(5)]
        self._insert_nodes(store, nodes)

        deleted = run(store.delete_by_metadata(user_id="u1"))
        assert deleted == 5

        # 确认没有残留
        for n in nodes:
            assert run(store.get_by_id(n.node_id)) is None

    def test_delete_idempotent(self, store):
        """重复删除同一组数据，第二次返回 0"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        self._insert_nodes(store, [n1])

        d1 = run(store.delete_by_metadata(user_id="u1"))
        assert d1 == 1

        d2 = run(store.delete_by_metadata(user_id="u1"))
        assert d2 == 0

    # --- delete_by_isolation_key 回归 ---

    def test_delete_by_isolation_key_exact(self, store):
        """delete_by_isolation_key 精确匹配，不是前缀匹配"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "a1", "s2", dims=self.DIMS)
        self._insert_nodes(store, [n1, n2])

        ik1 = n1.get_isolation_key()  # u1::a1::s1
        deleted = run(store.delete_by_isolation_key(ik1))
        assert deleted == 1

        # n1 删了，n2 还在
        assert run(store.get_by_id(n1.node_id)) is None
        assert run(store.get_by_id(n2.node_id)) is not None

    def test_delete_by_isolation_key_prefix_does_not_match(self, store):
        """传前缀 'u1::' 给 delete_by_isolation_key 应该匹配不到任何数据"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        self._insert_nodes(store, [n1])

        # 这正是旧 bug: client 传 "u1::" 给 delete_by_isolation_key
        deleted = run(store.delete_by_isolation_key("u1::"))
        assert deleted == 0  # 前缀匹配不到

        # 数据还在
        assert run(store.get_by_id(n1.node_id)) is not None


# ==================== Chroma 测试 ====================

class TestChromaDeleteByMetadata:
    """Chroma VectorStore 的 delete_by_metadata 测试"""

    DIMS = 32

    @pytest.fixture
    def store(self, tmp_path):
        """创建并初始化 Chroma VectorStore"""
        config = MemoryConfig.from_dict({
            "vector_store": {
                "provider": "chroma",
                "collection_name": "test_delete_chroma",
                "persist_directory": str(tmp_path / "chroma_data"),
                "embedding_dims": self.DIMS,
            },
        })
        from hy_memory.data.vector_store_chroma import ChromaVectorStore
        vs = ChromaVectorStore(config)
        run(vs.initialize())
        yield vs
        run(vs.close())

    def _insert_nodes(self, store, nodes: List[MemoryNode]):
        run(store.upsert_batch(nodes))

    def test_delete_by_user_id_only(self, store):
        """粒度1: 只传 user_id"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "a2", "s2", dims=self.DIMS)
        n3 = _make_node("u2", "a1", "s1", dims=self.DIMS)
        self._insert_nodes(store, [n1, n2, n3])

        deleted = run(store.delete_by_metadata(user_id="u1"))
        assert deleted == 2

        assert run(store.get_by_id(n1.node_id)) is None
        assert run(store.get_by_id(n2.node_id)) is None
        assert run(store.get_by_id(n3.node_id)) is not None

    def test_delete_by_user_and_agent(self, store):
        """粒度2: user_id + agent_id"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "a1", "s2", dims=self.DIMS)
        n3 = _make_node("u1", "a2", "s1", dims=self.DIMS)
        self._insert_nodes(store, [n1, n2, n3])

        deleted = run(store.delete_by_metadata(user_id="u1", agent_id="a1"))
        assert deleted == 2

        assert run(store.get_by_id(n1.node_id)) is None
        assert run(store.get_by_id(n2.node_id)) is None
        assert run(store.get_by_id(n3.node_id)) is not None

    def test_delete_by_user_agent_session(self, store):
        """粒度3: user_id + agent_id + session_id"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "a1", "s2", dims=self.DIMS)
        self._insert_nodes(store, [n1, n2])

        deleted = run(store.delete_by_metadata(user_id="u1", agent_id="a1", session_id="s1"))
        assert deleted == 1

        assert run(store.get_by_id(n1.node_id)) is None
        assert run(store.get_by_id(n2.node_id)) is not None

    def test_delete_empty_store(self, store):
        """空库删除返回 0"""
        deleted = run(store.delete_by_metadata(user_id="nonexistent"))
        assert deleted == 0

    def test_delete_by_isolation_key_returns_count(self, store):
        """Chroma delete_by_isolation_key 现在返回精确数量（不再返回 -1）"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        self._insert_nodes(store, [n1, n2])

        ik = n1.get_isolation_key()
        deleted = run(store.delete_by_isolation_key(ik))
        assert deleted == 2  # 精确计数，不是 -1

    def test_delete_by_isolation_key_prefix_does_not_match(self, store):
        """前缀不匹配任何数据"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        self._insert_nodes(store, [n1])

        deleted = run(store.delete_by_isolation_key("u1::"))
        assert deleted == 0
        assert run(store.get_by_id(n1.node_id)) is not None

    def test_delete_idempotent(self, store):
        """重复删除"""
        n1 = _make_node("u1", "a1", "s1", dims=self.DIMS)
        self._insert_nodes(store, [n1])

        d1 = run(store.delete_by_metadata(user_id="u1"))
        assert d1 == 1

        d2 = run(store.delete_by_metadata(user_id="u1"))
        assert d2 == 0


# ==================== 多用户隔离测试 ====================

class TestMultiUserIsolation:
    """多用户场景下的隔离性测试（FAISS）"""

    DIMS = 32

    @pytest.fixture
    def store(self, tmp_path):
        config = MemoryConfig.from_dict({
            "vector_store": {
                "provider": "faiss",
                "collection_name": "test_isolation",
                "persist_directory": str(tmp_path / "faiss_iso"),
                "embedding_dims": self.DIMS,
            },
        })
        from hy_memory.data.vector_store_faiss import FaissVectorStore
        vs = FaissVectorStore(config)
        run(vs.initialize())
        yield vs
        run(vs.close())

    def test_delete_one_user_does_not_affect_others(self, store):
        """删除 user_A 的全部记忆，不影响 user_B 和 user_C"""
        nodes_a = [_make_node("A", f"a{i}", f"s{i}", dims=self.DIMS) for i in range(3)]
        nodes_b = [_make_node("B", f"a{i}", f"s{i}", dims=self.DIMS) for i in range(3)]
        nodes_c = [_make_node("C", f"a{i}", f"s{i}", dims=self.DIMS) for i in range(3)]
        run(store.upsert_batch(nodes_a + nodes_b + nodes_c))

        deleted = run(store.delete_by_metadata(user_id="A"))
        assert deleted == 3

        # B 和 C 完好
        for n in nodes_b + nodes_c:
            assert run(store.get_by_id(n.node_id)) is not None

    def test_delete_one_agent_under_user(self, store):
        """同一用户下删除某个 agent，其他 agent 不受影响"""
        n1 = _make_node("u1", "chat", "s1", dims=self.DIMS)
        n2 = _make_node("u1", "chat", "s2", dims=self.DIMS)
        n3 = _make_node("u1", "work", "s1", dims=self.DIMS)
        n4 = _make_node("u1", "work", "s2", dims=self.DIMS)
        run(store.upsert_batch([n1, n2, n3, n4]))

        deleted = run(store.delete_by_metadata(user_id="u1", agent_id="chat"))
        assert deleted == 2

        assert run(store.get_by_id(n1.node_id)) is None
        assert run(store.get_by_id(n2.node_id)) is None
        assert run(store.get_by_id(n3.node_id)) is not None
        assert run(store.get_by_id(n4.node_id)) is not None

    def test_large_batch_delete(self, store):
        """批量插入 100 条后按 user 删除"""
        nodes = [_make_node("bulk_user", f"a{i%5}", f"s{i%10}", dims=self.DIMS) for i in range(100)]
        run(store.upsert_batch(nodes))

        deleted = run(store.delete_by_metadata(user_id="bulk_user"))
        assert deleted == 100

        # 全部删干净
        for n in nodes:
            assert run(store.get_by_id(n.node_id)) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
