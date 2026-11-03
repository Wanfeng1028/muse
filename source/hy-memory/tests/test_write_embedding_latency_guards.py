"""Write-path embedding latency guards.

These tests pin two regressions observed in staging:
1. OpenAI SDK retries must not be nested inside HY Memory retries.
2. An unchanged extracted memory must reuse the vector computed for reconcile search.
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
import pytest

from hy_memory.agent.reconciler import ReconcileOp, ReconcileResult
from hy_memory.agent.llm_provider import LLMProvider
from hy_memory.config import MemoryConfig
from hy_memory.core.embed_service import EmbedService
from hy_memory.models.memory import MemoryNode
from hy_memory.models.memory import MemoryLayer, MemoryStatus
from hy_memory.pipelines.base import WriteRequest
from hy_memory.pipelines.writer import MemoryWriter


@pytest.mark.asyncio
async def test_embed_http_attempts_equal_hy_memory_retry_budget(monkeypatch):
    """max_retries=2 means exactly three HTTP requests, not SDK 3 × outer 3."""
    import openai

    created_with = []
    requests_seen = 0

    class _Create:
        async def create(self, **kwargs):
            nonlocal requests_seen
            requests_seen += 1
            raise ConnectionError("temporary failure")

    class _Embeddings:
        def __init__(self):
            self.with_raw_response = _Create()

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            created_with.append(kwargs)
            self.embeddings = _Embeddings()

        async def close(self):
            return None

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeAsyncOpenAI)
    config = MemoryConfig.from_dict({
        "embedder": {
            "provider": "openai",
            "model": "test-embedding",
            "api_key": "test-key",
            "base_url": "http://embedding.test/v1",
            "embedding_dims": 3,
            "timeout": 1,
            "max_retries": 2,
            "retry_delay": 0,
        }
    })
    service = EmbedService(config)
    with pytest.raises(ConnectionError):
        await service.embed("one request budget")

    assert requests_seen == 3
    assert len(created_with) == 3  # retryable failure evicts the connection pool
    assert all(call["max_retries"] == 0 for call in created_with)


@pytest.mark.asyncio
async def test_embed_retries_transient_empty_json_response(monkeypatch):
    import json as json_module
    import openai

    calls = 0

    class _Create:
        async def create(self, **kwargs):
            nonlocal calls
            calls += 1
            raise json_module.JSONDecodeError("empty", "", 0)

    class _FakeClient:
        def __init__(self, **kwargs):
            self.embeddings = type("_Embeddings", (), {
                "with_raw_response": _Create(),
            })()

        async def close(self):
            return None

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeClient)
    config = MemoryConfig.from_dict({
        "embedder": {
            "provider": "openai", "model": "test", "api_key": "test",
            "base_url": "http://embedding.test/v1", "embedding_dims": 3,
            "timeout": 1, "max_retries": 2, "retry_delay": 0,
        }
    })
    with pytest.raises(json_module.JSONDecodeError):
        await EmbedService(config).embed("retry empty response")
    assert calls == 3


def test_embedding_cache_evicts_lru_and_accepts_new_entries():
    config = MemoryConfig.from_dict({"embedder": {"embedding_dims": 3}})
    service = EmbedService(config)
    service._embed_config.cache_size = 2

    service._cache_put("a", [1.0])
    service._cache_put("b", [2.0])
    assert service._cache_get("a") == [1.0]  # a becomes most recently used
    service._cache_put("c", [3.0])

    assert list(service._cache) == ["a", "c"]
    assert service._cache_get("b") is None


@pytest.mark.asyncio
async def test_full_embedding_cache_still_caches_new_text(monkeypatch):
    config = MemoryConfig.from_dict({"embedder": {"embedding_dims": 3}})
    service = EmbedService(config)
    service._embed_config.cache_size = 2
    calls = []

    async def _fake_embed(texts):
        calls.append(list(texts))
        return [[float(len(text)), 0.0, 0.0] for text in texts], [{} for _ in texts]

    monkeypatch.setattr(service, "_embed_texts_with_meta", _fake_embed)
    await service.embed("old-a")
    await service.embed("old-b")
    first = await service.embed("new-c")
    second = await service.embed("new-c")

    assert first == second
    assert calls == [["old-a"], ["old-b"], ["new-c"]]
    assert service.get_stats()["cache_size"] == 2


@pytest.mark.asyncio
async def test_llm_client_disables_sdk_retries_and_uses_configured_timeout(monkeypatch):
    import openai
    from unittest.mock import MagicMock

    created_with = []
    closed = 0

    def _fake_client(**kwargs):
        nonlocal closed
        created_with.append(kwargs)
        client = MagicMock()

        async def _create(**_kwargs):
            response = MagicMock()
            response.choices = [MagicMock(
                message=MagicMock(content="ok", tool_calls=None),
                finish_reason="stop",
            )]
            response.usage = MagicMock(
                prompt_tokens=1, completion_tokens=1, total_tokens=2,
            )
            response.model = "test-model"
            response.id = "resp-1"
            return response

        client.chat.completions.create = _create
        async def _close():
            nonlocal closed
            closed += 1
        client.close = _close
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", _fake_client)
    config = MemoryConfig.from_dict({
        "llm": {
            "provider": "openai", "model": "test-model", "api_key": "test",
            "timeout": 47, "max_retries": 2,
        }
    })
    provider = LLMProvider(config)
    response = await provider.complete("hello", max_tokens=8)
    second = await provider.complete("hello again", max_tokens=8)

    assert response.content == "ok"
    assert second.content == "ok"
    assert created_with == [{
        "api_key": "test", "base_url": None, "timeout": 47, "max_retries": 0,
    }]
    assert closed == 0
    await provider.close()
    assert closed == 1


@pytest.mark.asyncio
async def test_llm_non_retryable_400_stops_after_one_attempt(monkeypatch):
    import openai
    from unittest.mock import MagicMock

    calls = 0

    class _BadRequest(Exception):
        status_code = 400

    def _fake_client(**kwargs):
        client = MagicMock()

        async def _create(**_kwargs):
            nonlocal calls
            calls += 1
            raise _BadRequest("bad model")

        client.chat.completions.create = _create
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", _fake_client)
    config = MemoryConfig.from_dict({
        "llm": {
            "provider": "openai", "model": "bad-model", "api_key": "test",
            "timeout": 47, "max_retries": 3, "retry_delay": 10,
        }
    })
    with pytest.raises(Exception):
        await LLMProvider(config).complete("hello", max_tokens=8)
    assert calls == 1


@pytest.mark.asyncio
async def test_llm_reused_client_keeps_per_request_authorization(monkeypatch):
    import openai
    from unittest.mock import MagicMock

    created_with = []
    request_headers = []

    def _fake_client(**kwargs):
        created_with.append(kwargs)
        client = MagicMock()

        async def _create(**call_kwargs):
            request_headers.append(call_kwargs["extra_headers"]["Authorization"])
            response = MagicMock()
            response.choices = [MagicMock(
                message=MagicMock(content="ok", tool_calls=None),
                finish_reason="stop",
            )]
            response.usage = MagicMock(
                prompt_tokens=1, completion_tokens=1, total_tokens=2,
            )
            response.model = "test-model"
            response.id = "resp-1"
            return response

        client.chat.completions.create = _create
        client.close = MagicMock()
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", _fake_client)
    config = MemoryConfig.from_dict({
        "llm": {
            "provider": "aihub", "model": "test-model", "api_key": "base",
            "timeout": 47, "max_retries": 1,
        }
    })
    provider = LLMProvider(config)
    tokens = iter(("base?cache_task_id=one", "base?cache_task_id=two"))
    monkeypatch.setattr(
        provider, "_resolve_endpoint",
        lambda: (next(tokens), "http://llm/v1"),
    )

    await provider.complete("one", max_tokens=8)
    await provider.complete("two", max_tokens=8)

    assert created_with == [{
        "api_key": "base", "base_url": "http://llm/v1",
        "timeout": 47, "max_retries": 0,
    }]
    assert request_headers == [
        "Bearer base?cache_task_id=one",
        "Bearer base?cache_task_id=two",
    ]


@pytest.mark.asyncio
async def test_llm_transport_failure_evicts_cached_client(monkeypatch):
    import openai
    from unittest.mock import MagicMock

    created = []
    closed = []

    def _fake_client(**kwargs):
        index = len(created)
        client = MagicMock()

        async def _create(**_call_kwargs):
            if index == 0:
                raise ConnectionError("broken pooled connection")
            response = MagicMock()
            response.choices = [MagicMock(
                message=MagicMock(content="ok", tool_calls=None),
                finish_reason="stop",
            )]
            response.usage = MagicMock(
                prompt_tokens=1, completion_tokens=1, total_tokens=2,
            )
            response.model = "test-model"
            response.id = "resp-1"
            return response

        async def _close():
            closed.append(index)

        client.chat.completions.create = _create
        client.close = _close
        created.append(client)
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", _fake_client)
    config = MemoryConfig.from_dict({
        "llm": {
            "provider": "openai", "model": "test-model", "api_key": "test",
            "timeout": 47, "max_retries": 2, "retry_delay": 0,
        }
    })
    provider = LLMProvider(config)
    response = await provider.complete("hello", max_tokens=8)

    assert response.content == "ok"
    assert len(created) == 2
    assert closed == [0]
    await provider.close()
    assert closed == [0, 1]


class _RecordingEmbed:
    def __init__(self):
        self.batch_calls = []
        self.queued_calls = []

    async def embed_batch(self, texts):
        self.batch_calls.append(list(texts))
        return [[0.0, 1.0, 0.0] for _ in texts]

    async def embed_queued(self, text, use_cache=True):
        self.queued_calls.append(text)
        return [0.0, 1.0, 0.0]


class _RecordingStore:
    def __init__(self):
        self.nodes = []
        self.batch_calls = []
        self.update_batch_calls = []

    async def upsert(self, node: MemoryNode):
        self.nodes.append(node)
        return node.node_id

    async def upsert_batch(self, nodes):
        self.batch_calls.append(list(nodes))
        self.nodes.extend(nodes)
        return [node.node_id for node in nodes]

    async def update_payload_batch(self, updates_by_id):
        self.update_batch_calls.append(list(updates_by_id))
        return [node_id for node_id, _updates in updates_by_id]

    async def get_by_id(self, node_id):
        return next((n for n in self.nodes if n.node_id == node_id), None)

    async def get_embeddings(self, node_ids):
        return {}


@pytest.mark.asyncio
async def test_reconcile_is_serialized_per_user_without_candidate_precheck(monkeypatch):
    """Concurrent writes serialize, but every write still runs full reconcile."""
    config = MemoryConfig.from_dict({"vector_store": {"embedding_dims": 3}})
    writer = MemoryWriter.__new__(MemoryWriter)
    writer.config = config
    state = {"in_flight": 0, "max_in_flight": 0, "calls": 0}

    async def _locked(**kwargs):
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        state["calls"] += 1
        assert "skip_candidate_search" not in kwargs
        await asyncio.sleep(0.02)
        state["in_flight"] -= 1
        return [], None, {"add": 0, "supersede": 0, "update": 0, "total": 0}, {
            "prompt": 0, "completion": 0, "total": 0,
        }

    monkeypatch.setattr(writer, "_reconcile_and_store_locked", _locked)
    request = WriteRequest(content="raw", user_id="u-race", agent_id="a1")
    args = dict(
        new_memory_texts=["fact"], new_memories_meta=[{"content": "fact"}],
        request=request, vector_store=object(), req_id="req",
    )

    await asyncio.gather(
        writer._reconcile_and_store(**args),
        writer._reconcile_and_store(**args),
    )

    assert state["max_in_flight"] == 1
    assert state["calls"] == 2


class _NoopHybridRetriever:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def search_candidates(self, *args, **kwargs):
        type(self).calls += 1
        return []

    async def search_candidates_batch(self, query_texts, *args, **kwargs):
        type(self).calls += 1
        return [[] for _ in query_texts]


@pytest.mark.asyncio
async def test_reconciler_uses_precomputed_dedup_vectors(monkeypatch):
    """A PMV2-style multi-memory batch must not re-embed texts after dedup."""
    from hy_memory.agent.reconciler import MemoryReconciler
    from hy_memory.pipelines._retrieval import reconcile_retrieval

    monkeypatch.setattr(
        reconcile_retrieval, "ReconcileHybridRetriever", _NoopHybridRetriever,
    )
    _NoopHybridRetriever.calls = 0
    config = MemoryConfig.from_dict({"vector_store": {"embedding_dims": 3}})
    reconciler = MemoryReconciler(config)
    embed = _RecordingEmbed()
    texts = ["The user likes tea.", "The user rides a bicycle."]
    vectors = {
        texts[0]: [1.0, 0.0, 0.0],
        texts[1]: [0.0, 1.0, 0.0],
    }

    result = await reconciler.reconcile(
        new_memories=texts,
        user_id="u-latency",
        agent_id="default_agent",
        vector_store=object(),
        embed_service=embed,
        new_memory_embeddings=vectors,
    )

    assert result.success is True
    assert [op.op for op in result.ops] == ["ADD", "ADD"]
    assert result.new_memory_embeddings == vectors
    assert embed.batch_calls == []
    assert _NoopHybridRetriever.calls == 1


@pytest.mark.asyncio
async def test_writer_reuses_reconcile_embedding_for_unchanged_add():
    config = MemoryConfig.from_dict({"vector_store": {"embedding_dims": 3}})
    embed = _RecordingEmbed()
    store = _RecordingStore()
    writer = MemoryWriter(config, embed_service=embed, vector_store=store)

    content = "The user likes green tea."
    vector = [1.0, 0.0, 0.0]

    async def _fake_reconcile(*args, **kwargs):
        return ReconcileResult(
            ops=[ReconcileOp(op="ADD", content=content, layer="L2_FACT")],
            success=True,
            new_memory_embeddings={content: vector},
        )

    writer._reconciler = type("_Reconciler", (), {"reconcile": _fake_reconcile})()
    request = WriteRequest(
        content="raw",
        user_id="u-latency",
        agent_id="default_agent",
        session_id="s1",
    )

    stored_ids, error, counts, _tokens = await writer._reconcile_and_store_locked(
        new_memory_texts=[content],
        new_memories_meta=[{"content": content, "layer": "L2_FACT"}],
        request=request,
        vector_store=store,
        req_id="req-latency",
    )

    assert error is None
    assert len(stored_ids) == 1
    assert counts["add"] == 1
    assert embed.batch_calls == []
    assert embed.queued_calls == []
    assert store.nodes[0].embedding == vector


@pytest.mark.asyncio
async def test_writer_embeds_rewritten_reconcile_content_once():
    config = MemoryConfig.from_dict({"vector_store": {"embedding_dims": 3}})
    embed = _RecordingEmbed()
    store = _RecordingStore()
    writer = MemoryWriter(config, embed_service=embed, vector_store=store)

    extracted = "The user likes tea."
    rewritten = "The user likes green tea."

    async def _fake_reconcile(*args, **kwargs):
        return ReconcileResult(
            ops=[ReconcileOp(op="ADD", content=rewritten, layer="L2_FACT")],
            success=True,
            new_memory_embeddings={extracted: [1.0, 0.0, 0.0]},
        )

    writer._reconciler = type("_Reconciler", (), {"reconcile": _fake_reconcile})()
    request = WriteRequest(
        content="raw",
        user_id="u-latency",
        agent_id="default_agent",
        session_id="s1",
    )

    await writer._reconcile_and_store_locked(
        new_memory_texts=[extracted],
        new_memories_meta=[{"content": extracted, "layer": "L2_FACT"}],
        request=request,
        vector_store=store,
        req_id="req-latency-rewrite",
    )

    assert embed.batch_calls == [[rewritten]]
    assert embed.queued_calls == []


@pytest.mark.asyncio
async def test_multi_memory_vectors_flow_dedup_to_reconcile_to_store(monkeypatch):
    """The normal PMV2 path computes extracted-memory vectors only once."""
    from hy_memory.pipelines._retrieval import reconcile_retrieval

    monkeypatch.setattr(
        reconcile_retrieval, "ReconcileHybridRetriever", _NoopHybridRetriever,
    )
    _NoopHybridRetriever.calls = 0
    config = MemoryConfig.from_dict({"vector_store": {"embedding_dims": 3}})

    class _PipelineEmbed(_RecordingEmbed):
        async def embed_queued_with_meta(self, text):
            self.queued_calls.append(text)
            vector = (
                [1.0, 0.0, 0.0]
                if text == "The user likes tea."
                else [0.0, 1.0, 0.0]
            )
            return vector, {}

    embed = _PipelineEmbed()
    store = _RecordingStore()
    writer = MemoryWriter(config, embed_service=embed, vector_store=store)
    writer._reconciler = __import__(
        "hy_memory.agent.reconciler", fromlist=["MemoryReconciler"]
    ).MemoryReconciler(config)
    texts = ["The user likes tea.", "The user rides a bicycle."]
    metas = [{"content": text, "layer": "L2_FACT"} for text in texts]
    request = WriteRequest(
        content="raw", user_id="u-latency", agent_id="a1", session_id="s1",
    )

    texts, metas, vectors = await writer._dedup_extracted(
        texts, metas, request, "req-flow",
    )
    stored_ids, error, counts, _tokens = await writer._reconcile_and_store_locked(
        new_memory_texts=texts,
        new_memories_meta=metas,
        request=request,
        vector_store=store,
        req_id="req-flow",
        precomputed_embeddings=vectors,
    )

    assert error is None
    assert len(stored_ids) == 2
    assert counts["add"] == 2
    assert embed.batch_calls == []
    assert embed.queued_calls == texts
    assert _NoopHybridRetriever.calls == 1


@pytest.mark.asyncio
async def test_default_chroma_identical_second_write_does_not_add(monkeypatch):
    """Every write must search candidates; an exact duplicate produces zero ops."""
    from datetime import datetime

    from hy_memory.agent.llm_provider import LLMResponse
    from hy_memory.agent.reconciler import MemoryReconciler
    from hy_memory.data import vector_store_chroma as chroma_module
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    from hy_memory.pipelines._retrieval import reconcile_retrieval

    async def _direct_vdb_call(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(chroma_module, "_run_in_vdb_pool", _direct_vdb_call)

    class _DenseOnlyRetriever:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def search_candidates_batch(
            self, query_texts, query_embeddings, *, vector_store, user_id,
            agent_id, layers, **kwargs,
        ):
            type(self).calls += 1
            rows = []
            for embedding in query_embeddings:
                rows.append(await vector_store.search(
                    query_embedding=embedding,
                    user_id=user_id,
                    agent_ids=None,
                    layers=layers,
                    limit=20,
                    score_threshold=0.0,
                    status_filter=[MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED],
                    only_latest=False,
                ))
            return rows

    monkeypatch.setattr(
        reconcile_retrieval, "ReconcileHybridRetriever", _DenseOnlyRetriever,
    )

    class _DuplicateSkipLLM:
        def __init__(self):
            self.calls = []

        async def complete(self, prompt, **kwargs):
            self.calls.append(prompt)
            return LLMResponse(
                content="[]", prompt_tokens=1, completion_tokens=1,
                tokens_used=2, model="fake", finish_reason="stop",
            )

    class _FixedEmbed(_RecordingEmbed):
        async def embed(self, text, use_cache=True):
            return [1.0, 0.0, 0.0]

        async def embed_batch(self, texts, use_cache=True):
            self.batch_calls.append(list(texts))
            return [[1.0, 0.0, 0.0] for _ in texts]

        async def embed_queued(self, text, use_cache=True):
            self.queued_calls.append(text)
            return [1.0, 0.0, 0.0]

    with tempfile.TemporaryDirectory(prefix="hy-duplicate-write-") as root:
        config = MemoryConfig.from_dict({
            "vector_store": {
                "provider": "chroma",
                "collection_name": f"duplicate_{uuid.uuid4().hex[:8]}",
                "persist_directory": root,
                "embedding_dims": 3,
            },
        })
        store = ChromaVectorStore(config)
        await store.initialize()
        embed = _FixedEmbed()
        llm = _DuplicateSkipLLM()
        writer = MemoryWriter(
            config, embed_service=embed, vector_store=store, cache=None,
        )
        writer._vector_store = store
        writer._vector_store_initialized = True
        writer._reconciler = MemoryReconciler(config, llm_provider=llm)
        writer._reconciler._enable_search_query = False

        content = "The user swims every Saturday morning."

        async def _write(request_id):
            request = WriteRequest(
                content=content,
                user_id="duplicate-user",
                agent_id="default_agent",
                session_id=request_id,
                request_id=request_id,
                memory_at=datetime.now(),
            )
            return await writer._reconcile_and_store(
                new_memory_texts=[content],
                new_memories_meta=[{
                    "content": content, "layer": "L2_FACT", "tags": [],
                }],
                request=request,
                vector_store=store,
                req_id=request_id,
            )

        first_ids, first_error, first_counts, _ = await _write("first")
        second_ids, second_error, second_counts, _ = await _write("second")
        nodes = await store.list_by_user(
            user_id="duplicate-user",
            agent_id=None,
            layers=[MemoryLayer.L2_FACT],
            status_filter=None,
            with_vectors=False,
        )

        assert first_error is None
        assert first_counts["add"] == 1
        assert len(first_ids) == 1
        assert second_error is None
        assert second_ids == []
        assert second_counts == {
            "add": 0, "supersede": 0, "update": 0, "total": 0,
        }
        assert len(nodes) == 1
        assert nodes[0].node_id == first_ids[0]
        assert len(llm.calls) == 1
        assert first_ids[0] in llm.calls[0]
        assert _DenseOnlyRetriever.calls == 2

        await store.close()


@pytest.mark.asyncio
async def test_tag_embeddings_are_created_concurrently(monkeypatch):
    from hy_memory.pipelines._retrieval import tag_index

    monkeypatch.setattr(tag_index.config, "TAG_INDEX_WRITE_ENABLED", True)
    in_flight = 0
    max_in_flight = 0

    class _TagStore:
        async def has_tag_embedding(self, user_id, tag):
            return False

        async def upsert_tag_embedding(self, user_id, tag, embedding):
            return True

    class _TagEmbed:
        def __init__(self):
            self.calls = []

        async def embed_queued(self, text):
            nonlocal in_flight, max_in_flight
            self.calls.append(text)
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.03)
            in_flight -= 1
            return [1.0, 0.0, 0.0]

    embed = _TagEmbed()
    ok = await tag_index.ensure_tag_embeddings_for_node(
        vector_store=_TagStore(),
        embed_service=embed,
        user_id="u-tags",
        tags=["food", "preferences", "food"],
    )

    assert ok == 2
    assert max_in_flight == 2
    assert set(embed.calls) == {"food", "preferences"}


@pytest.mark.asyncio
async def test_tag_embeddings_use_batch_vdb_maintenance_when_supported(monkeypatch):
    from hy_memory.pipelines._retrieval import tag_index

    monkeypatch.setattr(tag_index.config, "TAG_INDEX_WRITE_ENABLED", True)

    class _BatchTagStore:
        def __init__(self):
            self.existing_calls = []
            self.batch_calls = []

        async def existing_tag_embeddings(self, user_id, tags):
            self.existing_calls.append((user_id, list(tags)))
            return ["food"]

        async def upsert_tag_embeddings_batch(self, user_id, items):
            self.batch_calls.append((user_id, dict(items)))
            return len(items)

    class _TagEmbed:
        def __init__(self):
            self.calls = []

        async def embed_queued(self, text):
            self.calls.append(text)
            return [1.0, 0.0, 0.0]

    store = _BatchTagStore()
    embed = _TagEmbed()
    ok = await tag_index.ensure_tag_embeddings_for_node(
        vector_store=store,
        embed_service=embed,
        user_id="u-tags",
        tags=["food", "preferences", "travel", "food"],
    )

    assert ok == 3
    assert store.existing_calls == [
        ("u-tags", ["food", "preferences", "travel"]),
    ]
    assert set(embed.calls) == {"preferences", "travel"}
    assert len(store.batch_calls) == 1
    assert set(store.batch_calls[0][1]) == {"preferences", "travel"}


@pytest.mark.asyncio
async def test_queued_batch_sends_duplicate_text_once(monkeypatch):
    config = MemoryConfig.from_dict({"embedder": {"embedding_dims": 3}})
    service = EmbedService(config)
    sent = []

    async def _fake_embed(texts):
        sent.append(list(texts))
        return (
            [[float(i), 0.0, 0.0] for i, _ in enumerate(texts)],
            [{} for _ in texts],
        )

    monkeypatch.setattr(service, "_embed_texts_with_meta", _fake_embed)
    loop = asyncio.get_running_loop()
    batch = [
        ("food", loop.create_future(), loop.time(), 0.0, 1),
        ("preferences", loop.create_future(), loop.time(), 0.0, 2),
        ("food", loop.create_future(), loop.time(), 0.0, 3),
    ]
    await service._send_batch(batch)

    assert sent == [["food", "preferences"]]
    results = [future.result() for _, future, *_ in batch]
    assert results[0][0] == results[2][0]
    assert all(meta["batch_unique_count"] == 2 for _, meta in results)


@pytest.mark.asyncio
async def test_queue_rearms_when_item_arrives_during_previous_flush(monkeypatch):
    """A request arriving during slow HTTP must not wait for a future enqueue."""
    config = MemoryConfig.from_dict({"embedder": {"embedding_dims": 3}})
    service = EmbedService(config)
    service._embed_config.queue_batch_window_ms = 5
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    batches = []

    async def _fake_embed(texts):
        batches.append(list(texts))
        if len(batches) == 1:
            first_started.set()
            await release_first.wait()
        return [[1.0, 0.0, 0.0] for _ in texts], [{} for _ in texts]

    monkeypatch.setattr(service, "_embed_texts_with_meta", _fake_embed)
    first = asyncio.create_task(service.embed_queued("first"))
    await asyncio.wait_for(first_started.wait(), timeout=0.2)
    second = asyncio.create_task(service.embed_queued("second"))
    await asyncio.sleep(0.02)
    release_first.set()

    assert await asyncio.wait_for(first, timeout=0.2) == [1.0, 0.0, 0.0]
    assert await asyncio.wait_for(second, timeout=0.2) == [1.0, 0.0, 0.0]
    assert batches == [["first"], ["second"]]


@pytest.mark.asyncio
async def test_qdrant_tag_collection_initializes_once_under_concurrency(monkeypatch):
    from types import SimpleNamespace
    from hy_memory.data import vector_store_qdrant as qdrant_module
    from hy_memory.data.vector_store_qdrant import QdrantVectorStore
    from hy_memory.pipelines._retrieval import bm25_fastembed

    config = MemoryConfig.from_dict({
        "vector_store": {"provider": "qdrant", "embedding_dims": 3},
    })
    store = QdrantVectorStore(config)
    created = 0

    class _Client:
        def get_collections(self):
            return SimpleNamespace(collections=[])

        def create_collection(self, **kwargs):
            nonlocal created
            created += 1

        def create_payload_index(self, **kwargs):
            return None

    store._client = _Client()
    monkeypatch.setattr(bm25_fastembed, "is_available", lambda: False)

    async def _direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(qdrant_module, "_run_in_vdb_pool", _direct)

    await asyncio.gather(
        store._ensure_tag_index_collection(),
        store._ensure_tag_index_collection(),
        store._ensure_tag_index_collection(),
    )

    assert created == 1


@pytest.mark.asyncio
async def test_apply_audit_skips_readback_unless_explicitly_enabled(monkeypatch):
    """Normal writes must not pay one VDB read per persisted memory."""
    monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "true")
    monkeypatch.setenv("MEMORY_WRITE_APPLY_VERIFY_ENABLED", "false")
    writer = MemoryWriter.__new__(MemoryWriter)
    emitted = []

    class _Store:
        reads = 0

        async def get_by_id(self, _memory_id):
            self.reads += 1
            return object()

    async def _emit(_request, **kwargs):
        emitted.append(kwargs)

    writer._emit_pipeline_step = _emit
    store = _Store()
    await writer._emit_reconcile_apply(
        WriteRequest(content="raw", user_id="u1"),
        vector_store=store,
        op_type="ADD",
        memory_id="m1",
        layer="l2_fact",
        content="fact",
    )

    assert store.reads == 0
    assert emitted[0]["parsed"]["verified"] is None
    assert emitted[0]["parsed"]["verification_skipped"] is True


@pytest.mark.asyncio
async def test_apply_audit_keeps_readback_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("MEMORY_WRITE_APPLY_VERIFY_ENABLED", "true")
    writer = MemoryWriter.__new__(MemoryWriter)
    emitted = []

    class _Store:
        reads = 0

        async def get_by_id(self, _memory_id):
            self.reads += 1
            return object()

    async def _emit(_request, **kwargs):
        emitted.append(kwargs)

    writer._emit_pipeline_step = _emit
    store = _Store()
    await writer._emit_reconcile_apply(
        WriteRequest(content="raw", user_id="u1"),
        vector_store=store,
        op_type="ADD",
        memory_id="m1",
        layer="l2_fact",
        content="fact",
    )

    assert store.reads == 1
    assert emitted[0]["parsed"]["verified"] is True
    assert emitted[0]["parsed"]["verification_skipped"] is False


@pytest.mark.asyncio
async def test_add_only_reconcile_uses_one_vector_store_batch(monkeypatch):
    monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "false")
    config = MemoryConfig.from_dict({"vector_store": {"embedding_dims": 3}})
    embed = _RecordingEmbed()
    store = _RecordingStore()
    writer = MemoryWriter(config, embed_service=embed, vector_store=store)
    texts = ["fact one", "fact two", "fact three"]

    async def _fake_reconcile(*args, **kwargs):
        return ReconcileResult(
            ops=[ReconcileOp(op="ADD", content=t, layer="L2_FACT") for t in texts],
            success=True,
            new_memory_embeddings={t: [1.0, 0.0, 0.0] for t in texts},
        )

    writer._reconciler = type("_Reconciler", (), {"reconcile": _fake_reconcile})()
    request = WriteRequest(content="raw", user_id="u-batch", agent_id="a1")
    ids, error, counts, _tokens = await writer._reconcile_and_store_locked(
        new_memory_texts=texts,
        new_memories_meta=[{"content": t, "layer": "L2_FACT"} for t in texts],
        request=request,
        vector_store=store,
        req_id="req-batch",
        precomputed_embeddings={t: [1.0, 0.0, 0.0] for t in texts},
    )

    assert error is None
    assert len(ids) == 3
    assert counts == {"add": 3, "supersede": 0, "update": 0, "total": 3}
    assert len(store.batch_calls) == 1
    assert len(store.batch_calls[0]) == 3


@pytest.mark.asyncio
async def test_qdrant_payload_and_vector_update_use_one_http_batch(monkeypatch):
    from hy_memory.data import vector_store_qdrant as qdrant_module
    from hy_memory.data.vector_store_qdrant import QdrantVectorStore

    config = MemoryConfig.from_dict({
        "vector_store": {"provider": "qdrant", "embedding_dims": 3},
    })
    store = QdrantVectorStore(config)
    calls = []

    class _Client:
        def retrieve(self, **kwargs):
            class _Point:
                payload = {"content": "original", "tags": []}

            return [_Point()]

        def batch_update_points(self, **kwargs):
            calls.append(("batch", kwargs))

        def set_payload(self, **kwargs):
            calls.append(("payload", kwargs))

        def update_vectors(self, **kwargs):
            calls.append(("vector", kwargs))

    store._client = _Client()

    async def _direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(qdrant_module, "_run_in_vdb_pool", _direct)
    ok = await store.update_payload(
        "node-1", {"content": "updated", "embedding": [1.0, 0.0, 0.0]},
    )

    assert ok is True
    assert [kind for kind, _kwargs in calls] == ["batch"]
    operations = calls[0][1]["update_operations"]
    assert len(operations) == 2


@pytest.mark.asyncio
async def test_update_only_reconcile_uses_one_vector_store_batch(monkeypatch):
    monkeypatch.setenv("MEMORY_WRITE_APPLY_VERIFY_ENABLED", "false")
    config = MemoryConfig.from_dict({"vector_store": {"embedding_dims": 3}})
    embed = _RecordingEmbed()
    store = _RecordingStore()
    writer = MemoryWriter(config, embed_service=embed, vector_store=store)
    targets = ["old-1", "old-2", "old-3"]
    texts = ["new one", "new two", "new three"]

    async def _fake_reconcile(*args, **kwargs):
        return ReconcileResult(
            ops=[
                ReconcileOp(op="UPDATE", memory_id=mid, content=text, layer="L2_FACT")
                for mid, text in zip(targets, texts)
            ],
            success=True,
            new_memory_embeddings={t: [1.0, 0.0, 0.0] for t in texts},
        )

    writer._reconciler = type("_Reconciler", (), {"reconcile": _fake_reconcile})()
    request = WriteRequest(content="raw", user_id="u-update", agent_id="a1")
    ids, error, counts, _tokens = await writer._reconcile_and_store_locked(
        new_memory_texts=texts,
        new_memories_meta=[{"content": t, "layer": "L2_FACT"} for t in texts],
        request=request,
        vector_store=store,
        req_id="req-update-batch",
        precomputed_embeddings={t: [1.0, 0.0, 0.0] for t in texts},
    )

    assert error is None
    assert ids == targets
    assert counts == {"add": 0, "supersede": 0, "update": 3, "total": 3}
    assert len(store.update_batch_calls) == 1
    assert [mid for mid, _updates in store.update_batch_calls[0]] == targets
