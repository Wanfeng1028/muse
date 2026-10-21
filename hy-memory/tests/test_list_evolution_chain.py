# -*- coding: utf-8 -*-
"""
list 返回演化链（R4 需求：结构化事实的更新过程可查、可展示）。

search 侧早有 evolution_chain，list 侧缺失。本次复用同一套 expand_evolution_chains，
保证两侧结构一致（前端可统一渲染）。

本文件锁死三件事：
1. 默认关闭——展开要按链逐条回查，不能拖慢默认列表。
2. 开启后只附加字段，绝不增删条目。expand_evolution_chains 为 search 设计，
   自带同链去重；list 若照单全收，同链多条时会少返回记录、与 total 对不上。
3. 只展开当前页，不是整表。
"""

import asyncio
import uuid

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.client import HyMemoryClient
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


DIMS = 32


def _node(content, *, node_id=None, is_latest=True, status=MemoryStatus.ACTIVE,
          supersedes=None, superseded_by=None, user_id="u1"):
    import random
    n = MemoryNode(
        node_id=node_id or str(uuid.uuid4()),
        user_id=user_id,
        agent_id="a1",
        session_id="s1",
        content=content,
        layer=MemoryLayer.L2_FACT,
        status=status,
        is_latest=is_latest,
    )
    n.supersedes = supersedes or []
    n.superseded_by = superseded_by or []
    vec = [random.gauss(0, 1) for _ in range(DIMS)]
    norm = sum(v * v for v in vec) ** 0.5
    n.embedding = [v / norm for v in vec]
    return n


@pytest.fixture
def faiss_store(tmp_path):
    config = MemoryConfig.from_dict({
        "vector_store": {
            "provider": "faiss",
            "collection_name": "test_evolution",
            "persist_directory": str(tmp_path / "faiss_data"),
            "embedding_dims": DIMS,
        },
    })
    from hy_memory.data.vector_store_faiss import FaissVectorStore
    vs = FaissVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


def _client_with(store):
    c = HyMemoryClient.__new__(HyMemoryClient)
    c._vector_store = store
    return c


def _seed_chain(store):
    """一条两节点的演化链 + 一条无链的独立记忆。

    head（ACTIVE/latest）supersedes old（SUPERSEDED），对应写入侧
    「矛盾取代」判定产生的结构。
    """
    old_id, head_id = str(uuid.uuid4()), str(uuid.uuid4())
    run(store.upsert_batch([
        _node("v1 用 Vue", node_id=old_id, is_latest=False,
              status=MemoryStatus.SUPERSEDED, superseded_by=[head_id]),
        _node("v2 改用 React", node_id=head_id, supersedes=[old_id]),
        _node("独立记忆"),
    ]))
    return old_id, head_id


class TestDefaultOff:
    def test_no_chain_field_by_default(self, faiss_store):
        _seed_chain(faiss_store)
        got = run(_client_with(faiss_store)._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=100, offset=0, order="desc",
        ))
        assert all("evolution_chain" not in m for m in got["memories"]), (
            "默认不得返回演化链——展开有回查成本，会拖慢默认列表"
        )


class TestWithEvolution:
    def test_chain_attached_to_head(self, faiss_store):
        old_id, head_id = _seed_chain(faiss_store)
        got = run(_client_with(faiss_store)._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=100, offset=0, order="desc",
            with_evolution=True,
        ))

        by_id = {m["memory_id"]: m for m in got["memories"]}
        chain = by_id[head_id].get("evolution_chain")
        assert chain, "链头必须带上演化链"
        assert [c["content"] for c in chain] == ["v2 改用 React", "v1 用 Vue"], (
            "顺序须为 latest → oldest，与 search 侧一致"
        )
        assert {"node_id", "content", "memory_at", "layer"} <= set(chain[0].keys())

    def test_unlinked_memory_has_no_chain_field(self, faiss_store):
        _seed_chain(faiss_store)
        got = run(_client_with(faiss_store)._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=100, offset=0, order="desc",
            with_evolution=True,
        ))
        solo = next(m for m in got["memories"] if m["content"] == "独立记忆")
        assert "evolution_chain" not in solo, "无链的记忆不应出现空字段"

    def test_item_count_and_total_unchanged(self, faiss_store):
        """开关不得影响条目数：历史版本是 SUPERSEDED，本就不在 list 里。"""
        _seed_chain(faiss_store)
        c = _client_with(faiss_store)
        base = run(c._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=100, offset=0, order="desc",
        ))
        with_evo = run(c._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=100, offset=0, order="desc",
            with_evolution=True,
        ))
        assert with_evo["total"] == base["total"] == 2
        assert len(with_evo["memories"]) == len(base["memories"])
        assert ({m["memory_id"] for m in with_evo["memories"]}
                == {m["memory_id"] for m in base["memories"]})

    def test_only_current_page_expanded(self, faiss_store):
        """分页后才展开：第二页的链不该在取第一页时被回溯。"""
        _seed_chain(faiss_store)
        calls = []
        orig = faiss_store.get_by_ids

        async def _counting(ids):
            calls.append(list(ids))
            return await orig(ids)

        faiss_store.get_by_ids = _counting
        got = run(_client_with(faiss_store)._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=1, offset=0, order="desc",
            with_evolution=True,
        ))
        assert len(got["memories"]) == 1
        # 首页若不含链头则一次回查都不该发生；含链头则最多回查该条链
        assert len(calls) <= 1

    def test_expand_failure_does_not_break_list(self, faiss_store):
        """演化链是附加信息，取不到也必须正常返回列表。"""
        _seed_chain(faiss_store)

        async def _boom(ids):
            raise RuntimeError("vdb down")

        faiss_store.get_by_ids = _boom
        got = run(_client_with(faiss_store)._list_vdb_bucket(
            user_id="u1", agent_id=None, limit=100, offset=0, order="desc",
            with_evolution=True,
        ))
        assert got["total"] == 2
        assert all("evolution_chain" not in m for m in got["memories"])
