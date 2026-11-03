# -*- coding: utf-8 -*-
"""
Entity store 端到端测试（chroma 后端）。

覆盖：
- entity 抽取（spaCy；模型缺失时 skip）；
- chroma entity store：0.95 cosine 合并、search、list、delete；
- index helper：抽取→embed→upsert；
- client.build_entity_store 迁移（旧数据补建）。
"""

import asyncio
import random
import uuid

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.pipelines._retrieval.entities import extract_entities, get_nlp_full


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _emb(dims: int = 32):
    vec = [random.gauss(0, 1) for _ in range(dims)]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


_SPACY_OK = get_nlp_full() is not None
_needs_spacy = pytest.mark.skipif(not _SPACY_OK, reason="spaCy en_core_web_sm not installed")


class _FakeEmbed:
    """确定性 fake embedder：同文本 → 同向量（哈希派生），不同文本近正交。"""
    def __init__(self, dims=32):
        self.dims = dims
        self._cache = {}

    def _vec(self, text):
        if text in self._cache:
            return list(self._cache[text])
        rnd = random.Random(hash(text) & 0xFFFFFFFF)
        v = [rnd.gauss(0, 1) for _ in range(self.dims)]
        n = sum(x * x for x in v) ** 0.5 or 1.0
        v = [x / n for x in v]
        self._cache[text] = v
        return list(v)

    async def embed_batch(self, texts):
        return [self._vec(t) for t in texts]

    async def embed(self, text):
        return self._vec(text)

    async def embed_queued(self, text, use_cache=True):
        return self._vec(text)


@pytest.fixture
def config(tmp_path):
    return MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_ent_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma_data"),
            "embedding_dims": 32,
        },
    })


@pytest.fixture
def store(config):
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    vs = ChromaVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


class TestEntityExtraction:
    @_needs_spacy
    def test_proper_and_compound(self):
        ents = extract_entities("User loves Kobe Bryant and machine learning")
        texts = {t for (_typ, t) in ents}
        assert "Kobe Bryant" in texts
        assert any("machine learning" == t for t in texts)

    @_needs_spacy
    def test_chinese_yields_empty(self):
        # 英文 spaCy 模型对中文几乎抽不到 entity（与 mem0 一致）
        assert extract_entities("用户喜欢科比，住在北京") == []

    def test_empty_input(self):
        assert extract_entities("") == []


class TestChromaEntityStore:
    def test_merge_search_list_delete(self, store):
        e = _emb()
        id1 = run(store.upsert_entity(entity_text="Kobe Bryant", entity_type="PROPER",
                                      embedding=list(e), memory_id="m1", user_id="u1", agent_id="a1"))
        id2 = run(store.upsert_entity(entity_text="Kobe Bryant", entity_type="PROPER",
                                      embedding=list(e), memory_id="m2", user_id="u1", agent_id="a1"))
        assert id1 == id2  # 0.95 cosine 合并
        id3 = run(store.upsert_entity(entity_text="Lakers", entity_type="PROPER",
                                      embedding=_emb(), memory_id="m3", user_id="u1", agent_id="a1"))
        assert id3 != id1

        hits = run(store.search_entities(query_embedding=list(e), user_id="u1", agent_ids=["a1"], top_k=10))
        kobe = [h for h in hits if h["data"] == "Kobe Bryant"][0]
        assert set(kobe["linked_memory_ids"]) == {"m1", "m2"}
        assert kobe["score"] > 0.99

        allents = run(store.list_entities(user_id="u1"))
        assert len(allents) == 2

        aff = run(store.delete_entities_for_memory(memory_id="m1", user_id="u1"))
        assert aff == 1
        hits2 = run(store.search_entities(query_embedding=list(e), user_id="u1", top_k=10))
        kobe2 = [h for h in hits2 if h["data"] == "Kobe Bryant"][0]
        assert kobe2["linked_memory_ids"] == ["m2"]

    def test_user_isolation(self, store):
        e = _emb()
        run(store.upsert_entity(entity_text="Kobe", entity_type="PROPER",
                                embedding=list(e), memory_id="m1", user_id="u1"))
        # 不同 user 查不到
        hits = run(store.search_entities(query_embedding=list(e), user_id="u2", top_k=10))
        assert hits == []


def _qdrant_available() -> bool:
    try:
        import qdrant_client  # noqa: F401
        return True
    except Exception:
        return False


_needs_qdrant = pytest.mark.skipif(not _qdrant_available(), reason="qdrant-client not installed")


@pytest.fixture
def qdrant_store(tmp_path):
    cfg = MemoryConfig.from_dict({
        "vector_store": {
            "provider": "qdrant",
            "collection_name": f"test_qent_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "qdrant_data"),
            "embedding_dims": 32,
        },
    })
    from hy_memory.data.vector_store_qdrant import QdrantVectorStore
    vs = QdrantVectorStore(cfg)
    run(vs.initialize())
    yield vs
    run(vs.close())


class TestQdrantEntityStore:
    """Qdrant 后端 entity store（dev6 漏实现，本类回归保护）。"""

    @_needs_qdrant
    def test_merge_search_list_delete(self, qdrant_store):
        store = qdrant_store
        e = _emb()
        id1 = run(store.upsert_entity(entity_text="Kobe Bryant", entity_type="PROPER",
                                      embedding=list(e), memory_id="m1", user_id="u1", agent_id="a1"))
        id2 = run(store.upsert_entity(entity_text="Kobe Bryant", entity_type="PROPER",
                                      embedding=list(e), memory_id="m2", user_id="u1", agent_id="a1"))
        assert id1 == id2  # 0.95 cosine 合并
        id3 = run(store.upsert_entity(entity_text="Lakers", entity_type="PROPER",
                                      embedding=_emb(), memory_id="m3", user_id="u1", agent_id="a1"))
        assert id3 != id1

        hits = run(store.search_entities(query_embedding=list(e), user_id="u1", agent_ids=["a1"], top_k=10))
        kobe = [h for h in hits if h["data"] == "Kobe Bryant"][0]
        assert set(kobe["linked_memory_ids"]) == {"m1", "m2"}
        assert kobe["score"] > 0.99

        allents = run(store.list_entities(user_id="u1"))
        assert len(allents) == 2

        aff = run(store.delete_entities_for_memory(memory_id="m1", user_id="u1"))
        assert aff == 1
        hits2 = run(store.search_entities(query_embedding=list(e), user_id="u1", top_k=10))
        kobe2 = [h for h in hits2 if h["data"] == "Kobe Bryant"][0]
        assert kobe2["linked_memory_ids"] == ["m2"]

    @_needs_qdrant
    def test_user_isolation(self, qdrant_store):
        store = qdrant_store
        e = _emb()
        run(store.upsert_entity(entity_text="Kobe", entity_type="PROPER",
                                embedding=list(e), memory_id="m1", user_id="u1"))
        assert run(store.search_entities(query_embedding=list(e), user_id="u2", top_k=10)) == []


class TestIndexHelper:
    @_needs_spacy
    def test_index_memory_entities(self, store):
        from hy_memory.pipelines._retrieval.entity_store import index_memory_entities
        emb = _FakeEmbed()
        cnt = run(index_memory_entities(
            vector_store=store, embed_service=emb,
            memory_id="m1", content="User loves Kobe Bryant and the Lakers",
            user_id="u1", agent_id="a1",
        ))
        assert cnt >= 1
        ents = run(store.list_entities(user_id="u1"))
        datas = {e["data"] for e in ents}
        assert any("Kobe" in d for d in datas)

    def test_no_entities_noop(self, store):
        from hy_memory.pipelines._retrieval.entity_store import index_memory_entities
        emb = _FakeEmbed()
        # 中文无 entity → 0，且不报错
        cnt = run(index_memory_entities(
            vector_store=store, embed_service=emb,
            memory_id="m1", content="用户喜欢科比", user_id="u1",
        ))
        assert cnt == 0


class TestBuildEntityStoreMigration:
    @_needs_spacy
    def test_build_from_existing_l2(self, config, store):
        # 先种两条旧 L2_FACT（不经 writer，模拟历史数据）
        emb = _FakeEmbed()
        for mid, content in [("m1", "User loves Kobe Bryant"),
                             ("m2", "User works at Notion as a product lead")]:
            n = MemoryNode(node_id=mid, user_id="u1", agent_id="default_agent", session_id="s1",
                           content=content, layer=MemoryLayer.L2_FACT,
                           status=MemoryStatus.ACTIVE, is_latest=True)
            n.embedding = _emb()
            run(store.upsert(n))

        # 手动构造一个最小 client 壳，调 async_build_entity_store 的核心逻辑
        from hy_memory.pipelines._retrieval.entity_store import index_memory_entities
        nodes = run(store.list_by_user(user_id="u1", agent_id="default_agent",
                                       status_filter=[MemoryStatus.ACTIVE],
                                       layers=[MemoryLayer.L2_FACT]))
        assert len(nodes) == 2
        indexed = 0
        for nd in nodes:
            indexed += run(index_memory_entities(
                vector_store=store, embed_service=emb,
                memory_id=nd.node_id, content=nd.content, user_id="u1", agent_id="default_agent",
            ))
        assert indexed >= 2
        ents = run(store.list_entities(user_id="u1"))
        assert len(ents) >= 2
