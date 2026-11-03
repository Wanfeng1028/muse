# -*- coding: utf-8 -*-
"""正文 NER → Graph Entity MENTIONS → 检索 boost。"""

import pytest

from hy_memory.data.graph_store_base import make_entity_id, normalize_entity_name
from hy_memory.models.memory import MemoryLayer, MemoryNode
from hy_memory.pipelines._graph.projector import project_memories_to_graph
from hy_memory.pipelines._retrieval.ner import (
    BOOST_ENTITY_LABELS,
    _get_nlp,
    extract_entities,
)
from hy_memory.pipelines._retrieval.scoring import score_vdb_node_additive

requires_spacy_model = pytest.mark.skipif(
    _get_nlp() is None,
    reason="spaCy English NER model is not installed",
)


def test_normalize_and_entity_id_stable():
    assert normalize_entity_name(" Tokyo ") == "tokyo"
    a = make_entity_id("u::a", "GPE", "Tokyo")
    b = make_entity_id("u::a", "GPE", "tokyo")
    assert a == b
    assert a.startswith("ent_")


def test_boost_labels_exclude_person():
    assert "PERSON" not in BOOST_ENTITY_LABELS
    assert "GPE" in BOOST_ENTITY_LABELS


def test_fused_max_tag_and_entity():
    # max(tag_cos, entity)=1.0 → +0.3
    s = score_vdb_node_additive(0.5, bm25_score=0.0, tag_cos=1.0, w_tag=0.3)
    assert abs(s - 0.8) < 1e-6


class _FakeEntityGraph:
    def __init__(self):
        self.nodes = []
        self.mentions = []
        self.cleared = []
        self.tags = []
        self.edges = []

    async def upsert_memory_node(self, node):
        self.nodes.append(node)
        return node.node_id

    async def add_topic_tag(self, node_id, topic, isolation_key, embed_service=None,
                            similarity_threshold=0.85):
        self.tags.append((node_id, topic))
        return f"topic_{topic}"

    async def clear_entity_mentions(self, memory_node_id):
        self.cleared.append(memory_node_id)
        before = len(self.mentions)
        self.mentions = [m for m in self.mentions if m[0] != memory_node_id]
        return before - len(self.mentions)

    async def add_entity_mention(self, memory_node_id, name, label, isolation_key):
        self.mentions.append((memory_node_id, name, label, isolation_key))
        return make_entity_id(isolation_key, label, name)

    async def add_edge(self, src, tgt, edge_type, properties=None):
        self.edges.append((src, tgt, edge_type))
        return True


@pytest.mark.asyncio
@requires_spacy_model
async def test_projector_content_tokyo_not_in_tags():
    """正文含 Tokyo、tags 无 Tokyo → 仍建 Entity MENTIONS；PERSON 不进。"""
    gs = _FakeEntityGraph()
    node = MemoryNode(
        node_id="m1", user_id="u1", agent_id="a1", session_id="s1",
        layer=MemoryLayer.L2_FACT,
        content="I visited Tokyo last summer and loved the food.",
        tags=["travel", "food"],  # 无 Tokyo
    )
    stats = await project_memories_to_graph(
        graph_store=gs, embed_service=None, nodes=[node],
    )
    assert stats["nodes"] == 1
    assert gs.cleared == ["m1"]
    names = {(n, lab) for _mid, n, lab, _ik in gs.mentions}
    # spaCy 应抽出 Tokyo/GPE；Evan 类 PERSON 不应出现
    assert any(n.casefold() == "tokyo" for n, _ in names), names
    assert all(lab != "PERSON" for _n, lab in names)
    assert "Tokyo" not in [t for _nid, t in gs.tags]


@pytest.mark.asyncio
async def test_projector_skips_person_only_content():
    gs = _FakeEntityGraph()
    node = MemoryNode(
        node_id="m2", user_id="u1", agent_id="a1", session_id="s1",
        layer=MemoryLayer.L2_FACT,
        content="Evan met Sam yesterday.",
        tags=["friendship"],
    )
    await project_memories_to_graph(
        graph_store=gs, embed_service=None, nodes=[node],
    )
    # PERSON 不在 BOOST → mentions 应为空（或仅有非 PERSON）
    assert all(lab != "PERSON" for _m, _n, lab, _ik in gs.mentions)


@pytest.mark.asyncio
@requires_spacy_model
async def test_kuzu_entity_roundtrip(tmp_path):
    from hy_memory.config import MemoryConfig, GraphStoreConfig
    from hy_memory.data.graph_store_kuzu import KuzuGraphStore
    from hy_memory.models.memory import MemoryStatus

    cfg = MemoryConfig()
    cfg.graph_store = GraphStoreConfig(
        provider="kuzu", db_path=str(tmp_path / "kuzu_entity"),
    )
    gs = KuzuGraphStore(cfg)
    await gs.initialize()
    if not getattr(gs, "_available", False):
        pytest.skip("Kuzu unavailable")

    node = MemoryNode(
        node_id="mem_tokyo", user_id="u1", agent_id="a1", session_id="s1",
        layer=MemoryLayer.L2_FACT,
        content="Day trip to Tokyo was amazing.",
        tags=["travel"],
    )
    node.status = MemoryStatus.ACTIVE

    stats = await project_memories_to_graph(
        graph_store=gs, embed_service=None, nodes=[node],
    )
    assert stats["nodes"] == 1
    assert stats["entities"] >= 1

    scope = node.get_topic_scope_key()
    hits = await gs.find_memories_by_entities(
        scope, [("Tokyo", "GPE")], limit=20,
    )
    assert "mem_tokyo" in {h["node_id"] for h in hits}

    # clear MENTIONS 后反查应空（UPDATE 重建依赖此能力）
    n = await gs.clear_entity_mentions("mem_tokyo")
    assert n >= 1
    hits2 = await gs.find_memories_by_entities(
        scope, [("Tokyo", "GPE")], limit=20,
    )
    assert "mem_tokyo" not in {h["node_id"] for h in hits2}

    await gs.close()
