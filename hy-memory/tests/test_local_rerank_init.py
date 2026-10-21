"""Local reranker initialization belongs to Client startup, never Search."""

from types import SimpleNamespace

import pytest

from hy_memory.client import HyMemoryClient
from hy_memory.config import MemoryConfig
from hy_memory.pipelines._retrieval.local_rerank import (
    DEFAULT_MODEL,
    LocalCrossEncoderReranker,
)


@pytest.fixture
def direct_to_thread(monkeypatch):
    async def _direct(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("hy_memory.utils.async_executor.to_thread_guarded", _direct)


class _FakeReranker:
    def __init__(self, *, fail=False):
        self.model_name = "fake/model"
        self.device = "cpu"
        self.fail = fail
        self.calls = 0

    def initialize(self):
        self.calls += 1
        if self.fail:
            raise ValueError("broken model")
        return {
            "model": self.model_name,
            "device": self.device,
            "load_ms": 12.0,
            "warmup_ms": 3.0,
        }


@pytest.mark.asyncio
async def test_client_skips_reranker_init_when_disabled(monkeypatch, direct_to_thread):
    client = HyMemoryClient.__new__(HyMemoryClient)
    client._config = MemoryConfig.from_dict({
        "recall": {"local_rerank_enabled": False},
    })
    called = False

    def _unexpected(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("disabled rerank must not create a model")

    from hy_memory.pipelines._retrieval import local_rerank

    monkeypatch.setattr(local_rerank, "get_local_reranker", _unexpected)
    await client._initialize_local_reranker()
    assert called is False


@pytest.mark.asyncio
async def test_client_initializes_and_waits_for_reranker(monkeypatch, direct_to_thread):
    client = HyMemoryClient.__new__(HyMemoryClient)
    client._config = MemoryConfig.from_dict({
        "recall": {
            "local_rerank_enabled": True,
            "local_rerank_model": "fake/model",
            "local_rerank_device": "cpu",
            "local_rerank_max_length": 128,
            "local_rerank_batch_size": 4,
        },
    })
    fake = _FakeReranker()
    captured = {}

    def _get(model_name, **kwargs):
        captured["model_name"] = model_name
        captured.update(kwargs)
        return fake

    from hy_memory.pipelines._retrieval import local_rerank

    monkeypatch.setattr(local_rerank, "get_local_reranker", _get)
    await client._initialize_local_reranker()

    assert fake.calls == 1
    assert captured == {
        "model_name": "fake/model",
        "device": "cpu",
        "max_length": 128,
        "batch_size": 4,
    }


@pytest.mark.asyncio
async def test_client_init_fails_fast_when_reranker_fails(
    monkeypatch, direct_to_thread,
):
    client = HyMemoryClient.__new__(HyMemoryClient)
    client._config = MemoryConfig.from_dict({
        "recall": {
            "local_rerank_enabled": True,
            "local_rerank_model": "fake/model",
        },
    })
    fake = _FakeReranker(fail=True)

    from hy_memory.pipelines._retrieval import local_rerank

    monkeypatch.setattr(local_rerank, "get_local_reranker", lambda *a, **k: fake)
    with pytest.raises(RuntimeError, match="initialization failed.*fake/model"):
        await client._initialize_local_reranker()
    assert fake.calls == 1


def test_score_never_lazy_loads_model():
    reranker = LocalCrossEncoderReranker("fake/model")
    assert reranker.initialized is False
    assert reranker.score("query", ["document"]) is None
    assert reranker.initialized is False


def test_default_model_is_small_multilingual_model():
    assert DEFAULT_MODEL == "nreimers/mmarco-mMiniLMv2-L6-H384-v1"


def test_initialize_loads_moves_and_warms_model(monkeypatch):
    calls = []

    class _Tensor:
        def to(self, device):
            calls.append(("tensor.to", device))
            return self

    class _Logits:
        def reshape(self, value):
            assert value == -1
            return self

        def detach(self):
            return self

        def cpu(self):
            return self

        def tolist(self):
            return [0.25]

    class _Tokenizer:
        def __call__(self, queries, documents, **kwargs):
            calls.append(("tokenize", queries, documents, kwargs))
            return {"input_ids": _Tensor()}

    class _Model:
        def eval(self):
            calls.append(("model.eval",))

        def to(self, device):
            calls.append(("model.to", device))

        def __call__(self, **kwargs):
            calls.append(("model.forward", tuple(kwargs)))
            return SimpleNamespace(logits=_Logits())

    class _AutoTokenizer:
        @staticmethod
        def from_pretrained(name):
            calls.append(("tokenizer.load", name))
            return _Tokenizer()

    class _AutoModel:
        @staticmethod
        def from_pretrained(name):
            calls.append(("model.load", name))
            return _Model()

    class _NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        no_grad=lambda: _NoGrad(),
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setitem(
        __import__("sys").modules,
        "transformers",
        SimpleNamespace(
            AutoModelForSequenceClassification=_AutoModel,
            AutoTokenizer=_AutoTokenizer,
        ),
    )

    reranker = LocalCrossEncoderReranker(
        "fake/model", device="auto", max_length=64, batch_size=2,
    )
    info = reranker.initialize()

    assert reranker.initialized is True
    assert reranker.device == "cpu"
    assert info["already_initialized"] is False
    assert ("tokenizer.load", "fake/model") in calls
    assert ("model.load", "fake/model") in calls
    assert ("model.to", "cpu") in calls
    assert any(call[0] == "model.forward" for call in calls)
    assert reranker.score("q", ["d"]) == [0.25]


def test_initialize_failure_does_not_leave_partial_model(monkeypatch):
    monkeypatch.setitem(
        __import__("sys").modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )

    class _BrokenTokenizer:
        @staticmethod
        def from_pretrained(name):
            raise OSError(f"cannot load {name}")

    monkeypatch.setitem(
        __import__("sys").modules,
        "transformers",
        SimpleNamespace(
            AutoModelForSequenceClassification=object(),
            AutoTokenizer=_BrokenTokenizer,
        ),
    )
    reranker = LocalCrossEncoderReranker("broken/model")

    with pytest.raises(RuntimeError, match="cannot load broken/model"):
        reranker.initialize()
    assert reranker.initialized is False
    assert reranker.load_error
