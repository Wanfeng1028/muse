"""Where a real HY client is allowed to send bytes, and where it is not.

The integration test goes beyond checking whether the config names a local
host. It verifies that a live HY instance doing real work opens no socket to
an external endpoint the user did not configure. SDK defaults can cover model,
graph, vector, and metrics services; a config assertion cannot rule out a code
path that reads those defaults directly.

So these tests watch the socket layer itself while a real client indexes and
searches. The first test is the control: it proves the watcher notices a
connection at all, because a watcher that sees nothing everywhere would pass
this file without meaning anything.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
from pathlib import Path

import pytest

from one_memory.hy_memory_bridge import (
    HyMemoryBridge,
    build_hy_memory_config,
)
from one_memory.model_profiles import ModelProfileSnapshot, ProviderKind


def local_onnx_profile() -> ModelProfileSnapshot:
    """A profile whose embedder runs in-process, so search needs no provider."""
    return ModelProfileSnapshot(
        profile_id="egress-integration",
        revision=1,
        provider_kind=ProviderKind.OLLAMA,
        base_url="http://127.0.0.1:11434",
        model="memory-model",
        embedding_model="builtin",
        embedding_provider_kind=ProviderKind.LOCAL_ONNX,
        embedding_base_url=None,
        embedding_dimensions=384,
        timeout_seconds=30,
        max_concurrency=1,
        context_window=8192,
        has_api_key=False,
    )


class Watcher:
    """Record every address the process tries to reach, and let it through.

    Recording rather than denying keeps the failure legible: a denied socket
    turns into whatever error the caller invents for it, while a recorded one
    names the host in the assertion.
    """

    def __init__(self, monkeypatch) -> None:
        self.targets: list[str] = []
        real_connect = socket.socket.connect
        real_resolve = socket.getaddrinfo

        def connect(sock, address, *args, **kwargs):
            self.targets.append(self._name(address))
            return real_connect(sock, address, *args, **kwargs)

        def resolve(host, port, *args, **kwargs):
            self.targets.append(f"{host}:{port}")
            return real_resolve(host, port, *args, **kwargs)

        monkeypatch.setattr(socket.socket, "connect", connect)
        monkeypatch.setattr(socket, "getaddrinfo", resolve)

    @staticmethod
    def _name(address: object) -> str:
        if isinstance(address, tuple) and len(address) >= 2:
            return f"{address[0]}:{address[1]}"
        return str(address)

    @property
    def hosts(self) -> set[str]:
        return {target.rsplit(":", 1)[0] for target in self.targets}


def test_the_watcher_reports_a_connection_that_really_happens(monkeypatch) -> None:
    """Control. Without this, an empty recording proves nothing."""
    watcher = Watcher(monkeypatch)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        client = socket.socket()
        client.settimeout(2)
        client.connect(listener.getsockname())
        client.close()
    finally:
        listener.close()

    assert "127.0.0.1" in watcher.hosts


def test_a_real_search_with_the_built_in_embedder_reaches_nothing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Search is local when the embedder is local, or the claim is wrong.

    A miss here means HY contacted an external endpoint the user never
    configured, which is the integration behavior that config assertions
    alone cannot verify.
    """
    pytest.importorskip("hy_memory")
    from one_memory.embedding_assets import assets_present

    if not assets_present():
        pytest.skip("built-in encoder weights are not installed")

    embedded = _count_local_embeds(monkeypatch)
    watcher = Watcher(monkeypatch)
    asyncio.run(_search(local_onnx_profile(), tmp_path))

    # An empty recording is only evidence if the search really ran. The
    # embedder loads lazily, so "reached nothing" and "did nothing" look the
    # same from the socket layer until we confirm a vector was produced.
    assert embedded, "the search never got as far as embedding the query"
    # Loopback to the configured Ollama port would still be a finding here:
    # search declares itself model-free, so it must not call the provider.
    assert watcher.targets == [], watcher.targets


def test_the_watcher_catches_a_remote_embedder_on_that_same_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Control: the SDK's remote embedding leaf is observable by the watcher.

    An empty memory store may short-circuit search before embedding, so the
    control calls the same configured EmbedService network leaf directly.
    """
    pytest.importorskip("hy_memory")
    from hy_memory.core.embed_service import EmbedService

    remote = local_onnx_profile().model_copy(
        update={
            "embedding_provider_kind": ProviderKind.OPENAI_COMPATIBLE,
            "embedding_base_url": "http://127.0.0.1:59/v1",
            "embedding_model": "remote-embedder",
            "has_api_key": True,
        }
    )
    config = build_hy_memory_config(remote, api_key="test-key", data_dir=tmp_path)
    service = EmbedService(config)
    watcher = Watcher(monkeypatch)
    with contextlib.suppress(Exception):
        asyncio.run(service.embed("synthetic remote embedding", use_cache=False))

    assert "127.0.0.1" in watcher.hosts, watcher.targets


def _count_local_embeds(monkeypatch) -> list[int]:
    """A truthy list once the in-process encoder has produced a vector."""
    from one_memory.hy_memory_bridge import LocalHyEmbedService

    seen: list[int] = []
    original = LocalHyEmbedService.embed

    async def counted(self, text, use_cache=True):
        vector = await original(self, text, use_cache)
        seen.append(len(vector))
        return vector

    monkeypatch.setattr(LocalHyEmbedService, "embed", counted)
    return seen


async def _search(
    profile: ModelProfileSnapshot,
    data_dir: Path,
    *,
    api_key: str | None = None,
) -> None:
    bridge = HyMemoryBridge(profile=profile, api_key=api_key, data_dir=data_dir)
    try:
        await bridge.search_ids("长期偏好", user_id="local", agent_id="*")
    finally:
        await bridge.close()


def test_no_internal_gateway_or_server_default_survives_our_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The SDK's shipped defaults must not be reachable through our config.

    Ambient SDK configuration may name remote stores and endpoints. We pin the
    OpenAI-compatible provider and local stores, so none may survive.
    """
    for name, value in (
        ("MEMORY_LLM_PROVIDER", "openai"),
        ("MEMORY_LLM_BASE_URL", "https://ambient.example/v1"),
        ("MEMORY_GRAPH_PROVIDER", "memgraph"),
        ("MEMGRAPH_URL", "bolt://memgraph.example.com:7687"),
        ("MEMORY_VECTOR_PROVIDER", "qdrant"),
        ("MEMORY_API_HOST", "0.0.0.0"),
    ):
        monkeypatch.setenv(name, value)

    config = build_hy_memory_config(local_onnx_profile(), api_key=None, data_dir=tmp_path)

    rendered = repr(config)
    for forbidden in ("ambient.example", "memgraph", "qdrant", "bolt://"):
        assert forbidden not in rendered.lower(), forbidden
    assert config.llm.provider == "openai"
    assert config.vector_store.provider == "chroma"
    assert config.graph_store.provider == "kuzu"
    assert str(tmp_path) in config.graph_store.db_path
