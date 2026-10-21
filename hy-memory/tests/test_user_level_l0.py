import asyncio
from datetime import datetime, timedelta

from hy_memory.agent.tools.basic_profile import (
    USER_LEVEL_AGENT_ID,
    _assemble_full_kv,
    _find_latest_l0,
    _user_lock,
    upsert_basic_profile,
)
from hy_memory.models.memory import MemoryLayer, MemoryNode, MemoryStatus
from hy_memory.pipelines._retrieval.user_level_l0 import (
    collapse_user_level_l0_hits,
    require_user_scope,
)


def run(coro):
    return asyncio.run(coro)


class FakeStore:
    def __init__(self, nodes=None):
        self.nodes = list(nodes or [])
        self.calls = []

    async def list_by_user(self, **kwargs):
        self.calls.append(kwargs)
        out = [n for n in self.nodes if n.user_id == kwargs.get("user_id")]
        layers = kwargs.get("layers")
        if layers:
            out = [n for n in out if n.layer in layers]
        statuses = kwargs.get("status_filter")
        if statuses:
            out = [n for n in out if n.status in statuses]
        return out[: kwargs.get("limit", len(out))]

    async def get_by_id(self, node_id):
        return next((n for n in self.nodes if n.node_id == node_id), None)

    async def upsert(self, node):
        self.nodes.append(node)

    async def update_payload(self, node_id, updates):
        node = await self.get_by_id(node_id)
        assert node is not None
        for key, value in updates.items():
            if key == "status" and isinstance(value, str):
                value = MemoryStatus(value)
            setattr(node, key, value)


class FakeEmbed:
    async def embed_queued(self, text):
        return [0.1] * 8


def l0(node_id, user, agent, kv, created, *, latest=True, status=MemoryStatus.ACTIVE):
    return MemoryNode(
        node_id=node_id,
        user_id=user,
        agent_id=agent,
        layer=MemoryLayer.L0_BASIC_INFO,
        content="profile",
        custom={"basic_info_kv": kv},
        gmt_created=created,
        is_latest=latest,
        status=status,
    )


def test_upsert_migrates_multiple_agent_chains_to_one_user_level_head():
    now = datetime.utcnow()
    old_a = l0("a", "u1", "agent-a", {"name": "Alice"}, now - timedelta(days=2))
    old_b = l0("b", "u1", "agent-b", {"employer": "Example Corp"}, now - timedelta(days=1))
    store = FakeStore([old_a, old_b])

    result = run(upsert_basic_profile(
        user_id="u1",
        kv={"employer": "Example Corp"}, vector_store=store,
        embed_service=FakeEmbed(), allowed_fields=["name", "employer"],
    ))

    assert result.success and result.created
    active = [n for n in store.nodes if n.status == MemoryStatus.ACTIVE and n.is_latest]
    assert len(active) == 1
    head = active[0]
    assert head.agent_id == USER_LEVEL_AGENT_ID
    assert head.session_id == ""
    assert set(head.supersedes or []) == {"a", "b"}
    assert head.custom["basic_info_kv"] == {"name": "Alice", "employer": "Example Corp"}
    assert "source_agent_id" not in head.custom
    assert old_a.status == MemoryStatus.SUPERSEDED and not old_a.is_latest
    assert old_b.status == MemoryStatus.SUPERSEDED and not old_b.is_latest


def test_repeated_updates_share_one_user_level_chain():
    store = FakeStore()
    first = run(upsert_basic_profile(
        user_id="u1", kv={"name": "Alice"},
        vector_store=store, embed_service=FakeEmbed(), allowed_fields=["name", "employer"],
    ))
    second = run(upsert_basic_profile(
        user_id="u1", kv={"employer": "Example Corp"},
        vector_store=store, embed_service=FakeEmbed(), allowed_fields=["name", "employer"],
    ))

    assert first.success and second.success
    active = [n for n in store.nodes if n.status == MemoryStatus.ACTIVE and n.is_latest]
    assert len(active) == 1
    assert active[0].agent_id == ""
    assert active[0].supersedes == [first.node_id]
    assert run(_assemble_full_kv(store, "u1", None)) == {
        "name": "Alice", "employer": "Example Corp"
    }
    assert run(_find_latest_l0(store, "u1")).node_id == second.node_id


def test_upsert_reads_l0_nodes_once():
    store = FakeStore()
    result = run(upsert_basic_profile(
        user_id="u1", kv={"name": "Alice"},
        vector_store=store, embed_service=FakeEmbed(), allowed_fields=["name"],
    ))

    assert result.success
    assert len(store.calls) == 1


def test_profile_recall_collapses_legacy_agent_heads_per_user():
    now = datetime.utcnow()
    old_a = l0("a", "u1", "agent-a", {"name": "Alice"}, now - timedelta(days=1))
    old_b = l0("b", "u1", "agent-b", {"employer": "Example Corp"}, now)
    schema = MemoryNode(
        node_id="schema", user_id="u1", agent_id="agent-a",
        layer=MemoryLayer.L6_SCHEMA, content="schema",
    )

    hits = collapse_user_level_l0_hits([
        {"node_id": "a", "node": old_a, "score": 0.9},
        {"node_id": "b", "node": old_b, "score": 0.8},
        {"node_id": "schema", "node": schema, "score": 0.7},
    ])

    l0_hits = [h for h in hits if h["node"].layer == MemoryLayer.L0_BASIC_INFO]
    assert len(l0_hits) == 1
    assert l0_hits[0]["node_id"] == "b"
    assert l0_hits[0]["score"] == 0.9
    assert l0_hits[0]["node"].agent_id == ""
    assert l0_hits[0]["node"].custom["basic_info_kv"] == {
        "name": "Alice", "employer": "Example Corp"
    }
    assert l0_hits[0]["user_level_merged"] is True
    assert len(hits) == 2


def test_canonical_user_level_head_beats_newer_legacy_head():
    now = datetime.utcnow()
    canonical = l0("canonical", "u1", "", {"name": "Alice"}, now - timedelta(days=1))
    legacy = l0("legacy", "u1", "agent-a", {"name": "Alice"}, now)
    hits = collapse_user_level_l0_hits([
        {"node_id": "canonical", "node": canonical, "score": 0.5},
        {"node_id": "legacy", "node": legacy, "score": 0.9},
    ])
    assert len(hits) == 1
    assert hits[0]["node_id"] == "canonical"
    assert hits[0]["score"] == 0.9


def test_user_lock_is_scoped_per_event_loop():
    async def get_lock():
        return _user_lock("u-loop")

    first = asyncio.run(get_lock())
    second = asyncio.run(get_lock())
    assert first is not second


def test_concurrent_writes_leave_one_user_level_head():
    class SlowStore(FakeStore):
        async def list_by_user(self, **kwargs):
            await asyncio.sleep(0.01)
            return await super().list_by_user(**kwargs)

        async def upsert(self, node):
            await asyncio.sleep(0.01)
            await super().upsert(node)

        async def update_payload(self, node_id, updates):
            await asyncio.sleep(0.01)
            await super().update_payload(node_id, updates)

    async def scenario():
        store = SlowStore()
        results = await asyncio.gather(
            upsert_basic_profile(
                user_id="u-race",
                kv={"name": "Alice"}, vector_store=store,
                embed_service=FakeEmbed(), allowed_fields=["name", "employer"],
            ),
            upsert_basic_profile(
                user_id="u-race",
                kv={"employer": "Example Corp"}, vector_store=store,
                embed_service=FakeEmbed(), allowed_fields=["name", "employer"],
            ),
        )
        return store, results

    store, results = run(scenario())
    assert all(result.success for result in results)
    active = [n for n in store.nodes if n.status == MemoryStatus.ACTIVE and n.is_latest]
    assert len(active) == 1
    assert active[0].agent_id == ""
    assert run(_assemble_full_kv(store, "u-race", None)) == {
        "name": "Alice", "employer": "Example Corp"
    }


def test_require_user_scope_returns_first_non_empty():
    assert require_user_scope(None, [], ["u1"]) == ["u1"]
    assert require_user_scope(["a"], ["b"]) == ["a"]


def test_require_user_scope_refuses_unscoped_l0_query():
    """L0 已无 agent/session 隔离，缺少 user 范围时必须拒绝查询而非全库扫描。"""
    assert require_user_scope(None, None, []) is None
