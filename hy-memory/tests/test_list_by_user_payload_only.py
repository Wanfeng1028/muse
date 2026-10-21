# -*- coding: utf-8 -*-
"""
list_by_user payload-only 调用点：`with_vectors=False` 是否真的传到了后端。

背景：VectorStoreBase.list_by_user 加了 `with_vectors` 开关（默认 True 保持
向后兼容），只需要 payload/tags/metadata 的调用点必须显式传 False，
避免把 embedding 一并拉回；否则一次列举可能顺带带回 MB 级向量。

本次修复覆盖的调用点（在 fix/list-by-user-without-vectors 分支上）：

client.py:
  - `_list_vdb_bucket`                 (list API，序列化为 list item)
  - `async_get_basic_info`             (只读 custom.basic_info_kv + 链)
  - `async_build_entity_store`         (只用 node_id/content 重建 entity)
  - `async_clone_user` 里 dst 空检查   (只判长度)

writer.py:
  - `_get_recent_history`              (只读 content/node_id/gmt_created)
  - `_collect_existing_tags`           (已在同一分支上覆盖)

basic_profile.py:
  - `_find_latest_l0`                  (只读 layer/custom/is_latest)
  - `_assemble_full_kv`                (只读 custom.basic_info_kv)

反向断言（必须保留 embedding 的调用点）：
  - `async_clone_user` src 全量复制    (embedding 会被 to_dict/from_dict 拷贝)
"""

from datetime import datetime, timedelta
import asyncio
import uuid

import pytest

from hy_memory.models.memory import (
    MemoryLayer,
    MemoryNode,
    MemoryStatus,
)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# fake vector store：抓 list_by_user 的每次 kwargs
# ---------------------------------------------------------------------------

class RecordingVectorStore:
    """只关心 list_by_user 传参；返回值可预置。"""

    def __init__(self, nodes=None):
        self.nodes = nodes or []
        self.calls = []  # 每次 list_by_user 的 kwargs
        self.get_calls = []

    async def list_by_user(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.nodes)

    async def get_by_id(self, node_id):
        self.get_calls.append(node_id)
        return None

    # 下列接口在部分调用路径里会被引用，给出安全的默认实现
    async def delete_entities_for_memory(self, **kwargs):
        return None

    async def upsert_batch(self, nodes):
        return [n.node_id for n in nodes]


def _basic_info_node(kv=None, is_latest=True, gmt_created=None):
    n = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id="u1",
        agent_id="a1",
        session_id="s1",
        content="basic info",
        layer=MemoryLayer.L0_BASIC_INFO,
        status=MemoryStatus.ACTIVE,
        is_latest=is_latest,
    )
    n.custom = {"basic_info_kv": kv or {"name": "alvin"}}
    n.gmt_created = gmt_created or datetime.utcnow()
    return n


def _summary_node(content, session_id="s1", memory_at=None):
    n = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id="u1",
        agent_id="a1",
        session_id=session_id,
        content=content,
        layer=MemoryLayer.L3_SUMMARY,
        status=MemoryStatus.ACTIVE,
    )
    n.memory_at = memory_at or datetime.utcnow()
    n.gmt_created = n.memory_at
    return n


def _l1_raw_node(content, gmt=None):
    n = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id="u1",
        agent_id="a1",
        session_id="s1",
        content=content,
        layer=MemoryLayer.L1_RAW,
        status=MemoryStatus.ACTIVE,
    )
    n.gmt_created = gmt or datetime.utcnow()
    return n


def _l2_fact_node(content):
    n = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id="u1",
        agent_id="a1",
        session_id="s1",
        content=content,
        layer=MemoryLayer.L2_FACT,
        status=MemoryStatus.ACTIVE,
    )
    return n


# ---------------------------------------------------------------------------
# basic_profile.py：_find_latest_l0 / _assemble_full_kv
# ---------------------------------------------------------------------------

class TestBasicProfilePayloadOnly:
    def test_find_latest_l0_omits_vectors(self):
        from hy_memory.agent.tools.basic_profile import _find_latest_l0
        store = RecordingVectorStore([_basic_info_node()])

        node = run(_find_latest_l0(store, user_id="u1"))

        assert node is not None
        assert len(store.calls) == 1
        assert store.calls[0].get("with_vectors") is False, (
            "_find_latest_l0 只用 layer/custom/is_latest 判定链头，不需要 embedding"
        )

    def test_assemble_full_kv_omits_vectors(self):
        from hy_memory.agent.tools.basic_profile import _assemble_full_kv
        store = RecordingVectorStore([
            _basic_info_node(kv={"name": "alvin"},
                             gmt_created=datetime.utcnow() - timedelta(days=1)),
            _basic_info_node(kv={"city": "sh"}, gmt_created=datetime.utcnow()),
        ])

        kv = run(_assemble_full_kv(
            store, user_id="u1", allowed_fields=None,
        ))

        assert kv == {"name": "alvin", "city": "sh"}
        assert len(store.calls) == 1
        assert store.calls[0].get("with_vectors") is False, (
            "_assemble_full_kv 只读 custom.basic_info_kv，不需要 embedding"
        )


# ---------------------------------------------------------------------------
# writer.py：_get_recent_history
# ---------------------------------------------------------------------------

class TestWriterPayloadOnly:
    def _writer(self):
        from hy_memory.pipelines.writer import MemoryWriter
        return MemoryWriter.__new__(MemoryWriter)

    def _request(self):
        from hy_memory.pipelines.writer import WriteRequest
        req = WriteRequest.__new__(WriteRequest)
        req.user_id = "u1"
        req.agent_id = "a1"
        req.session_id = "s1"
        req.memory_at = datetime.utcnow()
        return req


    def test_get_recent_history_omits_vectors(self):
        writer = self._writer()
        base = datetime.utcnow()
        store = RecordingVectorStore([
            _l1_raw_node("[user]: hi\n[assistant]: hello",
                         gmt=base - timedelta(seconds=2)),
            _l1_raw_node("[user]: how are you\n[assistant]: fine",
                         gmt=base - timedelta(seconds=1)),
        ])

        history = run(writer._get_recent_history(
            store, user_id="u1", agent_id="a1", max_turns=10,
        ))

        assert "hi" in history and "hello" in history
        assert len(store.calls) == 1
        assert store.calls[0].get("with_vectors") is False, (
            "_get_recent_history 只读 content/node_id/gmt_created，不需要 embedding"
        )


# ---------------------------------------------------------------------------
# client.py：_list_vdb_bucket / async_get_basic_info /
#            async_build_entity_store / async_clone_user (dst + src 反向断言)
# ---------------------------------------------------------------------------

class TestClientPayloadOnly:
    def _client_with(self, store):
        """构造一个只带最小 self 属性的裸 client 实例。

        真实 client 有 _loop_thread / _cache / _graph_store 等一堆运行时依赖；
        这里只测 list_by_user 的传参，其他埋点走 no-op。
        """
        from hy_memory.client import HyMemoryClient
        c = HyMemoryClient.__new__(HyMemoryClient)
        c._vector_store = store
        # 关掉 op_log 埋点（走 early return）
        c._cache = None
        # 关掉 graph store 埋点（多数方法只在 non-None 时才引用）
        c._graph_store = None
        return c

    def test_list_vdb_bucket_omits_vectors(self):
        store = RecordingVectorStore([])
        client = self._client_with(store)

        run(client._list_vdb_bucket(
            user_id="u1", agent_id="a1",
            limit=10, offset=0, order="desc",
        ))

        # user-level L0 需要额外一次不带 agent 的查询；两路都只读 payload。
        assert len(store.calls) == 2
        assert all(call.get("with_vectors") is False for call in store.calls), (
            "list API 只序列化 payload 到 list item，不需要 embedding"
        )
        assert "agent_id" not in store.calls[1] and "agent_ids" not in store.calls[1]

    def test_async_get_basic_info_omits_vectors(self, monkeypatch):
        # 避开 evolution 展开的额外 IO：patch 成透传恒等
        async def _fake_expand(vs, hits):
            return hits

        monkeypatch.setattr(
            "hy_memory.pipelines._retrieval.evolution.expand_evolution_chains",
            _fake_expand,
        )

        store = RecordingVectorStore([_basic_info_node()])
        client = self._client_with(store)

        # 公开方法带 @_ensure_internal_loop，需要 self._loop_thread；这里只验证 list_by_user 传参，
        # 绕过装饰器直接拿原函数（functools.wraps 保留在 __wrapped__）。
        from hy_memory.client import HyMemoryClient
        raw = HyMemoryClient.async_get_user_basic_info.__wrapped__
        result = run(raw(client, user_id="u1"))

        assert result["memories"], "至少要能取到一条 basic info"
        assert store.calls, "必须真的走了 list_by_user"
        assert store.calls[0].get("with_vectors") is False, (
            "async_get_user_basic_info 只读 custom.basic_info_kv/content/tags/chain"
        )

    def test_async_build_entity_store_omits_vectors(self, monkeypatch):
        # patch entity indexer：不真的 embed，只关心是否走对了 list 参数
        async def _fake_index(**kwargs):
            return 1

        monkeypatch.setattr(
            "hy_memory.pipelines._retrieval.entity_store.index_memory_entities",
            _fake_index,
        )

        store = RecordingVectorStore([_l2_fact_node("t1"), _l2_fact_node("t2")])
        client = self._client_with(store)
        client._embed_service = None  # index_memory_entities 已 patch

        from hy_memory.client import HyMemoryClient
        raw = HyMemoryClient.async_build_entity_store.__wrapped__
        result = run(raw(client, user_id="u1", agent_id="a1", rebuild=False))

        assert result["success"] is True
        assert result["memories_scanned"] == 2
        assert store.calls, "必须真的走了 list_by_user"
        assert store.calls[0].get("with_vectors") is False, (
            "entity rebuild 只用 node_id/content，重新 embed entity 名"
        )

    def test_async_clone_user_dst_check_omits_vectors_src_keeps_them(self):
        """Clone checks agent + user-level L0 on both source and destination.

        Destination checks are payload-only. Source reads must retain vectors:
        src 全量复制走 to_dict/from_dict 深拷贝，to_dict 会把 embedding 一并
        序列化到新节点；若 src 侧 with_vectors=False，克隆节点 embedding 会
        丢失，导致新用户后续 recall 命中率归零——这是绝对不能改的口径。
        """
        # 调用顺序：dst agent、dst L0、src agent、src L0。
        class _ClonefakeStore(RecordingVectorStore):
            async def list_by_user(self, *args, **kwargs):
                # dst 检查真实调用是位置参数 list_by_user(dst_user_id, agent_id=..., limit=1, with_vectors=False)
                # 归一化到 kwargs 记录，便于断言
                if args:
                    kwargs = {**kwargs, "user_id": args[0]}
                self.calls.append(kwargs)
                # 目标侧两次检查都返回空。
                if len(self.calls) <= 2:
                    return []
                # 源侧返回一条带 embedding 的节点。
                node = MemoryNode(
                    node_id=str(uuid.uuid4()),
                    user_id="src",
                    agent_id="a1",
                    session_id="s1",
                    content="src memory",
                    layer=MemoryLayer.L2_FACT,
                    status=MemoryStatus.ACTIVE,
                )
                node.embedding = [0.1] * 16
                return [node]

            async def upsert_batch(self, nodes):
                self._upserted = list(nodes)
                return [n.node_id for n in nodes]

            async def delete_by_metadata(self, **kwargs):
                # rollback 兜底，返回 no-op
                return 0

        store = _ClonefakeStore()
        client = self._client_with(store)

        from hy_memory.client import HyMemoryClient
        raw = HyMemoryClient.async_clone_user.__wrapped__
        result = run(raw(
            client, src_user_id="src", dst_user_id="dst", agent_id="a1",
        ))

        assert result["success"] is True, result
        assert len(store.calls) == 4

        # dst agent + dst user-level L0：只判存在性，不需要 embedding。
        assert all(call.get("with_vectors") is False for call in store.calls[:2])

        # src agent + src user-level L0：必须默认（未传，等价于 True）。
        assert all(call.get("with_vectors", True) is True for call in store.calls[2:])

        # 顺带确认写入的新节点真的带了 embedding
        assert hasattr(store, "_upserted") and store._upserted, "src 必须真的 upsert 了"
        assert store._upserted[0].embedding, "克隆节点必须保留 embedding"
