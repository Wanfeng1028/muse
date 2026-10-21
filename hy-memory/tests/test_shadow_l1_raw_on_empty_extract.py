# -*- coding: utf-8 -*-
"""
L1_RAW 降级 SHADOW 的触发条件（writer._run_agent 末段）。

背景：extractor 判定「这段对话没有可提取的用户事实」（纯技术问答等）时返回
memory=[]，此前 `if stored_ids and memory_id` 使 stored_ids 为空 → 不降级，
L1_RAW 长期停在 ACTIVE 被 list / search / keyword_search 召回。

本测试锁定五条语义：
  1. 提取为空（success=True, memory=[]）→ **应降级**（本次修复点）
  2. 提取失败（success=False，如 EMPTY_RESPONSE）→ **不降级**，留 ACTIVE 待重试
  3. 正常提取到内容 → 仍降级（回归保护，原行为不变）
  4. 显式指定非 raw 层（metadata 传 extra["layer"]）→ **不降级**，
     否则等于逻辑删除调用方刚写入的数据
  5. 降级时 upsert 抛错 → 不影响本次写入判定成功（容错保持）
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.pipelines.base import WriteRequest, WriteResponse


# ---------------------------------------------------------------- fakes


@dataclass
class _FakeAgentResult:
    """只带 _run_agent 实际读取的字段，避免依赖 AgentResult 的构造细节。"""

    success: bool = True
    extracted_info: Dict[str, Any] = field(default_factory=dict)
    suggested_layer: Optional[str] = None
    summary: Optional[str] = None
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    should_merge: bool = False
    merge_target_id: Optional[str] = None
    tokens_used: int = 0
    extract_elapsed_ms: float = 1.0
    summary_elapsed_ms: float = 0.0
    error: Optional[str] = None
    error_code: Optional[str] = None


class _FakeMemAgent:
    def __init__(self, result: _FakeAgentResult):
        self._result = result

    async def process_add(self, **kwargs):
        return self._result


class _FakeVectorStore:
    """内存 VDB。记录每次 upsert 时的 (node_id, status)，供断言降级是否发生。"""

    def __init__(self, fail_upsert: bool = False):
        self.nodes: Dict[str, MemoryNode] = {}
        self.upsert_calls: List[tuple] = []
        self._fail_upsert = fail_upsert

    async def upsert(self, node: MemoryNode) -> str:
        if self._fail_upsert:
            raise RuntimeError("vdb down")
        nid = node.node_id or uuid.uuid4().hex
        node.node_id = nid
        self.nodes[nid] = node
        self.upsert_calls.append((nid, node.status))
        return nid

    async def get_by_id(self, node_id: str) -> Optional[MemoryNode]:
        return self.nodes.get(node_id)

    async def search(self, *a, **kw):
        return []

    async def list_by_user(self, *a, **kw):
        return []


class _FakeEmbed:
    async def embed_batch(self, texts):
        return [[0.0] * 8 for _ in texts]

    async def embed_queued(self, text):
        return [0.0] * 8


# ---------------------------------------------------------------- harness


def _build_writer(agent_result: _FakeAgentResult, store: _FakeVectorStore):
    """构造一个只用于跑 _run_agent 的 writer。

    cache=None 使各 pipeline log 直接 return（`_write_extract_log` 首行判空），
    因此不依赖 sqlite / 可观测性安装。
    """
    from hy_memory.config import MemoryConfig
    from hy_memory.pipelines.writer import MemoryWriter

    cfg = MemoryConfig()
    w = MemoryWriter(cfg, embed_service=_FakeEmbed(), vector_store=store, cache=None)
    w._mem_agent = _FakeMemAgent(agent_result)
    w._vector_store = store
    # 提取到内容时走 _direct_store 分支即可（不需要真跑 reconcile LLM）
    w._reconcile_and_store = _stub_store          # type: ignore[assignment]
    w._direct_store = _stub_store                 # type: ignore[assignment]
    return w


async def _stub_store(**kwargs):
    """(stored_ids, recon_error, ops_counts, recon_tokens)"""
    metas = kwargs.get("new_memories_meta") or []
    ids = [f"fact-{i}" for i in range(len(metas))]
    return ids, None, {}, {}


def _mk_node(layer: MemoryLayer = MemoryLayer.L1_RAW) -> MemoryNode:
    return MemoryNode(
        node_id="raw-1",
        user_id="u1",
        agent_id="default_agent",
        session_id="s1",
        content="你能直接 git 仓库吗",
        layer=layer,
        status=MemoryStatus.ACTIVE,
        is_latest=True,
    )


class _Span:
    """tracer span 占位（_run_agent 只调这两个方法）。"""

    def set_output(self, *a, **kw):
        pass

    def set_error(self, *a, **kw):
        pass


def _run_agent(agent_result: _FakeAgentResult,
               node: Optional[MemoryNode] = None,
               store: Optional[_FakeVectorStore] = None,
               extra: Optional[Dict[str, Any]] = None,
               memory_id: Optional[str] = None,
               upsert_store: Optional[_FakeVectorStore] = None,
               request_id: str = "req-test"):
    """跑一次 _run_agent，返回 (mem_node, response, store)。

    upsert_store: 传入时用它作为 _run_agent 的 vector_store 参数
                  （用于模拟降级写库失败），store 仍作为 writer 的内部 store。
    memory_id:    默认取 node.node_id；传空串可模拟 L1 写入失败的场景。
    """
    node = node or _mk_node()
    store = store or _FakeVectorStore()
    store.nodes[node.node_id] = node

    w = _build_writer(agent_result, store)
    req = WriteRequest(
        content=node.content,
        user_id="u1",
        agent_id="default_agent",
        session_id="s1",
        extra=dict(extra or {}),
        request_id=request_id,
    )
    resp = WriteResponse(success=True)

    asyncio.run(
        w._run_agent(
            request=req,
            response=resp,
            vector_store=upsert_store or store,
            mem_node=node,
            memory_id=node.node_id if memory_id is None else memory_id,
            tracer_span=_Span(),
        )
    )
    return node, resp, store


# ---------------------------------------------------------------- tests


class TestShadowOnEmptyExtract:
    def test_empty_extract_still_shadows_l1_raw(self):
        """提取为空（正常结论）也要降级 —— 本次修复的核心语义。"""
        node, resp, store = _run_agent(
            _FakeAgentResult(success=True, extracted_info={"memory": [], "intentions": []})
        )

        assert resp.extra["agent_status"] == "success"
        assert resp.extra["agent_nodes"] == 0, "空提取不应产出高层节点"
        assert node.status == MemoryStatus.SHADOW, "空提取时 L1_RAW 仍应降级"
        assert (node.node_id, MemoryStatus.SHADOW) in store.upsert_calls

    def test_failed_extract_keeps_active(self):
        """提取失败保持 ACTIVE：数据可能还有救，留档待重试。"""
        node, resp, store = _run_agent(
            _FakeAgentResult(
                success=False,
                extracted_info={},
                error="empty response",
                error_code="EMPTY_RESPONSE",
            )
        )

        assert resp.extra["agent_status"] == "failed"
        assert node.status == MemoryStatus.ACTIVE, "提取失败不得降级"
        assert all(s != MemoryStatus.SHADOW for _, s in store.upsert_calls)

    def test_successful_extract_still_shadows(self):
        """回归保护：正常提取到内容时的降级行为不变。"""
        node, resp, store = _run_agent(
            _FakeAgentResult(
                success=True,
                extracted_info={"memory": [{"content": "用户在学吉他", "layer": "L2_FACT"}]},
            )
        )

        assert resp.extra["agent_status"] == "success"
        assert resp.extra["agent_nodes"] >= 1
        assert node.status == MemoryStatus.SHADOW

    def test_explicit_non_raw_layer_is_not_shadowed(self):
        """调用方显式指定非 raw 层时不得降级 —— 否则等于逻辑删除其刚写入的数据。

        layer 由 metadata 透传进 extra（client.async_add 的 metadata 原样进 extra），
        此处直接用 L2_FACT 节点模拟该场景。

        用「提取到内容」而非「提取为空」：只有前者才会走到降级分支，
        才真正验证 layer 守卫生效（提取为空时旧条件本身也不降级，测不出区别）。
        """
        node, resp, store = _run_agent(
            _FakeAgentResult(
                success=True,
                extracted_info={"memory": [{"content": "用户在学吉他", "layer": "L2_FACT"}]},
            ),
            node=_mk_node(layer=MemoryLayer.L2_FACT),
            extra={"layer": MemoryLayer.L2_FACT.value},
        )

        assert resp.extra["agent_status"] == "success"
        assert resp.extra["agent_nodes"] >= 1, "本用例须走到降级分支才有意义"
        assert node.status == MemoryStatus.ACTIVE, "非 L1_RAW 节点不得被降级"

    def test_shadow_upsert_failure_does_not_fail_write(self):
        """降级写库失败只告警，不改变本次写入的成功判定。"""
        node, resp, _ = _run_agent(
            _FakeAgentResult(success=True, extracted_info={"memory": []}),
            upsert_store=_FakeVectorStore(fail_upsert=True),
            request_id="req-shadow-fail",
        )

        # 降级失败被 except 吞掉，agent 仍判定 success
        assert resp.extra["agent_status"] == "success"
        assert node.status == MemoryStatus.SHADOW, (
            "status 在内存里已改（upsert 才失败）——此处只断言写入判定不受影响"
        )


class TestShadowGuards:
    def test_no_memory_id_skips_shadow(self):
        """L1 写入失败时 memory_id 为空串，不应尝试降级。"""
        node, resp, store = _run_agent(
            _FakeAgentResult(success=True, extracted_info={"memory": []}),
            memory_id="",
            request_id="req-no-mid",
        )

        assert resp.extra["agent_status"] == "success"
        assert node.status == MemoryStatus.ACTIVE
        assert all(s != MemoryStatus.SHADOW for _, s in store.upsert_calls)
