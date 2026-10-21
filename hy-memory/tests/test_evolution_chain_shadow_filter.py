# -*- coding: utf-8 -*-
"""演化链展开时屏蔽 SHADOW 节点。

dedup 从「硬删」改为「置 SHADOW」（逻辑删除、可恢复）后出现一条泄漏路径：

  _trace_full_chain 走 get_by_ids 按 node_id 直取，**不看 status**；被去重的
  节点其 supersedes / superseded_by 链接也还在。于是只要链上另一个节点被召回，
  刚被去重"删掉"的内容就会经 evolution_chain 重新返回给用户。

更严重的是：dedup 判重链头时会连带处理整条链（chain_node_ids），整链被 SHADOW
后所有节点 is_latest 都是 False，_trace_full_chain 挑 head 的逻辑会退化成
`max(all_nodes, key=_time_key)` —— 直接交回一个 SHADOW 节点当代表节点。

本文件锁住：
  - 链上个别 SHADOW 节点不出现在 evolution_chain 里；
  - 代表节点取「可见链」的链头，不会是 SHADOW；
  - 整条链都不可见时该 hit 被丢弃（而不是 fallback 回原始 hit 返回 SHADOW）；
  - 正常链（无 SHADOW）行为不变。
"""

import asyncio
import random
import uuid

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.pipelines._retrieval.evolution import expand_evolution_chains


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _emb(dims=32):
    v = [random.gauss(0, 1) for _ in range(dims)]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


@pytest.fixture
def config(tmp_path):
    return MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_shadowchain_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma"),
            "embedding_dims": 32,
        },
        "cache": {"backend": "sqlite"},
    })


@pytest.fixture
def store(config):
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    vs = ChromaVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


def _node(store, *, content, status, is_latest, supersedes=None, emb=None):
    n = MemoryNode(
        user_id="u1", agent_id="a1", session_id="s1",
        layer=MemoryLayer.L2_FACT, content=content, owner="user",
        status=status, is_latest=is_latest,
        supersedes=supersedes,
        embedding=emb or _emb(),
    )
    return run(store.upsert(n)), n


def _link(store, old_id, new_id):
    """回填 superseded_by，建立双向链（与 writer.py SUPERSEDE 路径一致）。"""
    run(store.update_payload(old_id, {"superseded_by": [new_id]}))


def _hit(store, node_id, score=0.9):
    node = run(store.get_by_id(node_id))
    return {"node_id": node_id, "score": score, "node": node}


class TestShadowFilteredFromChain:
    def test_shadow_body_not_exposed_in_chain(self, store):
        """链身被 SHADOW（如 dedup 判掉一个非链头重复项）→ 不出现在 chain 里。"""
        e = _emb()
        old_id, _ = _node(store, content="v1 old", status=MemoryStatus.SHADOW,
                          is_latest=False, emb=e)
        mid_id, _ = _node(store, content="v2 mid", status=MemoryStatus.SUPERSEDED,
                          is_latest=False, supersedes=[old_id], emb=e)
        head_id, _ = _node(store, content="v3 head", status=MemoryStatus.ACTIVE,
                           is_latest=True, supersedes=[mid_id], emb=e)
        _link(store, old_id, mid_id)
        _link(store, mid_id, head_id)

        out = run(expand_evolution_chains(store, [_hit(store, head_id)]))
        assert len(out) == 1
        contents = [c["content"] for c in out[0]["evolution_chain"]]
        assert "v3 head" in contents
        assert "v2 mid" in contents
        assert "v1 old" not in contents, "SHADOW 链身不应出现在 evolution_chain"

    def test_representative_node_is_never_shadow(self, store):
        """链头被 SHADOW、链身仍 ACTIVE 时，代表节点必须是可见的那个。"""
        e = _emb()
        body_id, _ = _node(store, content="visible body", status=MemoryStatus.ACTIVE,
                           is_latest=False, emb=e)
        head_id, _ = _node(store, content="shadowed head", status=MemoryStatus.SHADOW,
                           is_latest=False, supersedes=[body_id], emb=e)
        _link(store, body_id, head_id)

        out = run(expand_evolution_chains(store, [_hit(store, body_id)]))
        assert len(out) == 1
        rep = out[0]["node"]
        assert rep.status != MemoryStatus.SHADOW, "代表节点不能是 SHADOW"
        assert rep.content == "visible body"
        assert all(
            c["content"] != "shadowed head"
            for c in out[0]["evolution_chain"]
        )

    def test_fully_shadowed_chain_is_dropped(self, store):
        """整条链被 dedup SHADOW → 该 hit 直接丢弃，不返回任何 SHADOW 内容。

        这是最关键的一条：整链 SHADOW 后 is_latest 全为 False，
        _trace_full_chain 会退化成按时间取 head，交回一个 SHADOW 节点。
        若调用方 fallback 回原始 hit，等于把逻辑删除的内容返回给用户。
        """
        e = _emb()
        old_id, _ = _node(store, content="dup old", status=MemoryStatus.SHADOW,
                          is_latest=False, emb=e)
        new_id, _ = _node(store, content="dup new", status=MemoryStatus.SHADOW,
                          is_latest=False, supersedes=[old_id], emb=e)
        _link(store, old_id, new_id)

        out = run(expand_evolution_chains(store, [_hit(store, old_id)]))
        assert out == [], f"整链 SHADOW 应丢弃该 hit，实际返回 {out}"

    def test_fully_shadowed_chain_dropped_even_when_hit_is_head(self, store):
        """从链头侧命中同样要丢弃（避免只在某个方向上生效）。"""
        e = _emb()
        old_id, _ = _node(store, content="d1", status=MemoryStatus.SHADOW,
                          is_latest=False, emb=e)
        new_id, _ = _node(store, content="d2", status=MemoryStatus.SHADOW,
                          is_latest=False, supersedes=[old_id], emb=e)
        _link(store, old_id, new_id)

        out = run(expand_evolution_chains(store, [_hit(store, new_id)]))
        assert out == []

    def test_mixed_hits_only_shadowed_chain_dropped(self, store):
        """同一批里有正常链和全 SHADOW 链 → 只丢后者，不影响前者。"""
        e1, e2 = _emb(), _emb()
        # 正常链
        ok_old, _ = _node(store, content="ok v1", status=MemoryStatus.SUPERSEDED,
                          is_latest=False, emb=e1)
        ok_head, _ = _node(store, content="ok v2", status=MemoryStatus.ACTIVE,
                           is_latest=True, supersedes=[ok_old], emb=e1)
        _link(store, ok_old, ok_head)
        # 全 SHADOW 链
        bad_old, _ = _node(store, content="bad v1", status=MemoryStatus.SHADOW,
                           is_latest=False, emb=e2)
        bad_new, _ = _node(store, content="bad v2", status=MemoryStatus.SHADOW,
                           is_latest=False, supersedes=[bad_old], emb=e2)
        _link(store, bad_old, bad_new)

        out = run(expand_evolution_chains(
            store, [_hit(store, ok_head), _hit(store, bad_old)]
        ))
        assert len(out) == 1
        assert out[0]["node"].content == "ok v2"

    def test_normal_chain_unaffected(self, store):
        """无 SHADOW 的链行为不变（防止过滤逻辑误伤正常路径）。"""
        e = _emb()
        old_id, _ = _node(store, content="n v1", status=MemoryStatus.SUPERSEDED,
                          is_latest=False, emb=e)
        head_id, _ = _node(store, content="n v2", status=MemoryStatus.ACTIVE,
                           is_latest=True, supersedes=[old_id], emb=e)
        _link(store, old_id, head_id)

        # 从链身命中，应展开并以链头为代表
        out = run(expand_evolution_chains(store, [_hit(store, old_id)]))
        assert len(out) == 1
        assert out[0]["node"].node_id == head_id
        assert out[0]["is_evolved"] is True
        assert [c["content"] for c in out[0]["evolution_chain"]] == ["n v2", "n v1"]

    def test_non_chain_hit_passes_through(self, store):
        """不在链上的普通节点原样返回，不受影响。"""
        nid, _ = _node(store, content="standalone", status=MemoryStatus.ACTIVE,
                       is_latest=True)
        out = run(expand_evolution_chains(store, [_hit(store, nid)]))
        assert len(out) == 1
        assert out[0]["node"].content == "standalone"
        assert not out[0].get("is_evolved")
