# -*- coding: utf-8 -*-
"""
R2：调用方自定义 meta 的透传与 merge 追加。

需求口径（CTX）：
- meta 为 list，一个记忆节点可挂多份，每份代表「该次 write 时刻」的上下文
- add（新增记忆）：直接用本次传入的 meta；一次 write 产生多条新增时各条都带同一份
- merge（合并到已有记忆）：追加到旧节点的 meta list 上，**保留旧 meta，不覆盖**
- meta 不 embed、不参与召回、不作过滤条件

本文件锁死上述语义，以及「不传 meta 时与改动前逐字一致」这条向后兼容契约。
"""

import asyncio
import inspect

import pytest

from hy_memory.client import HyMemoryClient
from hy_memory.pipelines.base import WriteRequest
from hy_memory.pipelines.writer import MemoryWriter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _req(meta=None):
    return WriteRequest(content="x", client_meta=meta)


class _Op:
    """够用的 reconcile op 替身：_build_custom 只碰 supersede_reason。"""

    def __init__(self, supersede_reason=None):
        self.supersede_reason = supersede_reason


META1 = {"source_platform": "codebuddy", "has_tool_call": True, "scene": "chat"}
META2 = {"source_platform": "workbuddy", "has_tool_call": False, "scene": "review"}


class TestWriteRequestField:
    def test_client_meta_defaults_to_none(self):
        assert WriteRequest(content="x").client_meta is None

    def test_client_meta_is_separate_from_extra(self):
        """extra 混放 SDK 控制键（agent_mode / mode / layer），合用会互相覆盖。"""
        req = WriteRequest(content="x", extra={"mode": "pro"}, client_meta={"mode": "biz"})
        assert req.extra == {"mode": "pro"}
        assert req.client_meta == {"mode": "biz"}


class TestAddEntrypoint:
    def test_async_add_exposes_meta(self):
        params = inspect.signature(HyMemoryClient.async_add).parameters
        assert "meta" in params
        assert params["meta"].default is None

    def test_sync_add_exposes_meta(self):
        params = inspect.signature(HyMemoryClient.add).parameters
        assert "meta" in params
        assert params["meta"].default is None


class TestBuildCustomOnNewNode:
    """新建节点（ADD / SUPERSEDE / 直写 / summary / intention）只带本次 meta。"""

    def test_meta_wrapped_in_list(self):
        custom = MemoryWriter._build_custom(_Op(), "rid-1", _req(META1))
        assert custom["meta"] == [META1], "单份 meta 也必须是 list，读侧才不用分支"

    def test_no_meta_key_when_not_provided(self):
        """不传 meta 时 custom 必须与改动前逐字一致，不能多出空键。"""
        custom = MemoryWriter._build_custom(_Op(), "rid-1", _req(None))
        assert custom == {"request_id": "rid-1"}

    def test_no_meta_key_when_request_absent(self):
        assert MemoryWriter._build_custom(_Op(), "rid-1") == {"request_id": "rid-1"}

    def test_empty_meta_treated_as_absent(self):
        assert "meta" not in MemoryWriter._build_custom(_Op(), "rid-1", _req({}))

    def test_coexists_with_internal_keys(self):
        custom = MemoryWriter._build_custom(_Op("contradiction"), "rid-1", _req(META1))
        assert custom == {
            "request_id": "rid-1",
            "supersede_reason": "contradiction",
            "meta": [META1],
        }

    def test_meta_is_copied_not_referenced(self):
        """存进 custom 后再改原 dict 不应影响已落库内容。"""
        src = dict(META1)
        custom = MemoryWriter._build_custom(_Op(), "rid-1", _req(src))
        src["scene"] = "mutated"
        assert custom["meta"][0]["scene"] == "chat"

    def test_op_may_be_none(self):
        """summary / intention 等路径没有 reconcile op。"""
        custom = MemoryWriter._build_custom(None, "rid-1", _req(META1))
        assert custom["meta"] == [META1]


class TestMergeAppendSemantics:
    """UPDATE 原地改同一节点，旧 meta 必须保留——这是 R2 的核心契约。"""

    def test_appends_to_existing_chain(self):
        merged = MemoryWriter._merge_client_meta({"meta": [META1]}, _req(META2))
        assert merged["meta"] == [META1, META2], "旧 meta 必须保留在前，新的追加在后"

    def test_accumulates_across_multiple_writes(self):
        custom = {"meta": [META1]}
        for i in range(3):
            custom = MemoryWriter._merge_client_meta(custom, _req({"n": i}))
        assert custom["meta"] == [META1, {"n": 0}, {"n": 1}, {"n": 2}]

    def test_first_meta_on_node_without_any(self):
        merged = MemoryWriter._merge_client_meta({"request_id": "old"}, _req(META1))
        assert merged["meta"] == [META1]

    def test_preserves_other_custom_keys(self):
        """custom 是整体替换写回的，内部字段不能被 meta 合并冲掉。"""
        merged = MemoryWriter._merge_client_meta(
            {"request_id": "old-rid", "basic_info_kv": {"name": "ivan"}, "meta": [META1]},
            _req(META2),
        )
        assert merged["request_id"] == "old-rid"
        assert merged["basic_info_kv"] == {"name": "ivan"}
        assert merged["meta"] == [META1, META2]

    def test_returns_none_when_no_meta_passed(self):
        """返回 None 是「无需回读与写回」的信号，保证未用该功能者零额外开销。"""
        assert MemoryWriter._merge_client_meta({"meta": [META1]}, _req(None)) is None

    def test_handles_missing_old_custom(self):
        assert MemoryWriter._merge_client_meta(None, _req(META1))["meta"] == [META1]

    def test_non_list_legacy_meta_is_not_dropped(self):
        """历史数据里 meta 可能是裸 dict；降级成首元素，不能静默丢。"""
        merged = MemoryWriter._merge_client_meta({"meta": META1}, _req(META2))
        assert merged["meta"] == [META1, META2]

    def test_does_not_mutate_input(self):
        old = {"meta": [META1]}
        MemoryWriter._merge_client_meta(old, _req(META2))
        assert old == {"meta": [META1]}, "回读到的旧 custom 不应被就地改写"


class TestUpdateAppendsThroughStore:
    """端到端走一遍存储：UPDATE 分支必须真的把追加后的 meta 写回节点。

    上面的用例只覆盖纯函数，无法证明 writer 调用了它、也无法证明 custom 被写进
    update_payload。R2 的核心风险恰恰在这里——漏写回就会静默丢掉旧 meta。
    """

    DIMS = 32

    def _emb(self):
        import random

        vec = [random.gauss(0, 1) for _ in range(self.DIMS)]
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    def _store(self, tmp_path):
        import uuid as _uuid

        from hy_memory.config import MemoryConfig
        from hy_memory.data.vector_store_faiss import FaissVectorStore

        cfg = MemoryConfig.from_dict({
            "vector_store": {
                "provider": "faiss",
                "collection_name": f"test_meta_{_uuid.uuid4().hex[:8]}",
                "persist_directory": str(tmp_path / "faiss_meta"),
                "embedding_dims": self.DIMS,
            },
        })
        store = FaissVectorStore(cfg)
        _run(store.initialize())
        return cfg, store

    def _writer(self, cfg, store, ops):
        from hy_memory.agent.reconciler import ReconcileResult
        from hy_memory.pipelines.writer import MemoryWriter

        writer = MemoryWriter(cfg, vector_store=store)
        _run(writer.initialize())

        outer = self

        class _FakeEmbed:
            async def embed_batch(self, texts):
                return [outer._emb() for _ in texts]

            async def embed_queued(self, text, use_cache=True):
                return outer._emb()

        writer._embed_service = _FakeEmbed()

        async def _fake_reconcile(*args, **kwargs):
            return ReconcileResult(ops=ops)

        writer.reconciler.reconcile = _fake_reconcile
        return writer

    def _seed(self, store, custom):
        import uuid as _uuid

        from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus

        node = MemoryNode(
            node_id=str(_uuid.uuid4()), user_id="u1", agent_id="default_agent",
            session_id="s1", content="用户用 React。", layer=MemoryLayer.L2_FACT,
            status=MemoryStatus.ACTIVE, is_latest=True, owner="user",
            custom=custom,
        )
        node.embedding = self._emb()
        _run(store.upsert(node))
        return node

    def _update_op(self, node_id, content="用户用 React 18 + TS。"):
        from hy_memory.agent.reconciler import ReconcileOp

        return ReconcileOp(
            op="UPDATE", memory_id=node_id, content=content,
            owner="user", tags=[], layer="L2_FACT",
        )

    def _write(self, writer, store, ops, meta):
        req = WriteRequest(content="x", user_id="u1", agent_id="default_agent",
                           client_meta=meta)
        _run(writer._reconcile_and_store(
            new_memory_texts=["用户用 React 18 + TS。"],
            new_memories_meta=[{"content": "用户用 React 18 + TS。", "layer": "L2_FACT",
                                "tags": [], "owner": "user"}],
            request=req, vector_store=store, req_id="rid-new",
        ))

    def test_update_appends_to_existing_meta(self, tmp_path):
        cfg, store = self._store(tmp_path)
        node = self._seed(store, {"request_id": "rid-old", "meta": [META1]})
        writer = self._writer(cfg, store, [self._update_op(node.node_id)])

        self._write(writer, store, None, META2)

        got = _run(store.get_by_id(node.node_id))
        assert got.custom.get("meta") == [META1, META2], (
            f"旧 meta 必须保留并追加新的，实际 {got.custom.get('meta')}"
        )
        assert got.content == "用户用 React 18 + TS。", "记忆本体仍需正常更新"

    def test_update_without_meta_leaves_custom_untouched(self, tmp_path):
        """不传 meta 时不得触碰 custom——这是对存量写入路径的零影响保证。"""
        cfg, store = self._store(tmp_path)
        node = self._seed(store, {"request_id": "rid-old", "meta": [META1]})
        writer = self._writer(cfg, store, [self._update_op(node.node_id)])

        self._write(writer, store, None, None)

        got = _run(store.get_by_id(node.node_id))
        assert got.custom.get("meta") == [META1], "没传 meta 却改动了已有 meta"
        assert got.custom.get("request_id") == "rid-old"

    def test_update_on_node_without_meta(self, tmp_path):
        cfg, store = self._store(tmp_path)
        node = self._seed(store, {"request_id": "rid-old"})
        writer = self._writer(cfg, store, [self._update_op(node.node_id)])

        self._write(writer, store, None, META1)

        got = _run(store.get_by_id(node.node_id))
        assert got.custom.get("meta") == [META1]
        assert got.custom.get("request_id") == "rid-old", "内部字段不能被合并冲掉"

    def test_add_carries_single_meta(self, tmp_path):
        from hy_memory.agent.reconciler import ReconcileOp

        cfg, store = self._store(tmp_path)
        op = ReconcileOp(op="ADD", content="用户用 Vue。", owner="user",
                         tags=[], layer="L2_FACT")
        writer = self._writer(cfg, store, [op])

        self._write(writer, store, None, META1)

        nodes = _run(store.list_by_user(user_id="u1"))
        added = [n for n in nodes if n.content == "用户用 Vue。"]
        assert len(added) == 1
        assert added[0].custom.get("meta") == [META1]


class TestReadPathsExposeMeta:
    """list / search / get 三处都要在顶层给 meta，读侧才不用为不同接口写两套。"""

    def test_list_item_exposes_meta(self):
        from hy_memory.models.memory import MemoryNode, MemoryLayer

        node = MemoryNode(
            node_id="n1", user_id="u1", layer=MemoryLayer.L2_FACT, content="c",
            custom={"request_id": "rid", "meta": [META1]},
        )
        item = HyMemoryClient._memory_node_to_list_item(node)
        assert item["meta"] == [META1]

    def test_list_item_meta_empty_when_absent(self):
        from hy_memory.models.memory import MemoryNode, MemoryLayer

        node = MemoryNode(node_id="n1", user_id="u1", layer=MemoryLayer.L2_FACT, content="c")
        assert HyMemoryClient._memory_node_to_list_item(node)["meta"] == []

    def test_readers_expose_meta_from_custom(self):
        """两个 reader 的共享主流程必须透出 meta。"""
        import hy_memory.pipelines.reader_base as reader_base

        src = inspect.getsource(reader_base)
        assert '"meta"' in src and 'get("meta")' in src

    def test_readers_do_not_leak_whole_custom(self):
        """custom 含 request_id 等内部字段，不能整份塞进 search 返回项。"""
        import hy_memory.pipelines.reader_base as reader_base

        src = inspect.getsource(reader_base)
        assert '"custom": ' not in src
