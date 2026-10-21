"""Expect local ONNX embedding to be the default and to feed HY Memory.

HY's EmbedService only speaks OpenAI-compatible HTTP and offers no injection
point. After the client is built we replace `_embed_service` with a thin
adapter around LocalEmbedder — in every place that holds one, including the
pipelines HY pre-warms during construction.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from one_memory.embedding_assets import (
    BUILTIN_EMBEDDING_DIMENSIONS,
    BUILTIN_EMBEDDING_MODEL,
)
from one_memory.hy_memory_bridge import (
    LocalHyEmbedService,
    build_hy_memory_config,
    create_hy_memory_client,
)
from one_memory.local_embedding import LocalEmbedder
from one_memory.model_profiles import (
    ModelProfileInput,
    ModelProfileStore,
    ProviderKind,
    apply_builtin_embedding_defaults,
)
from one_memory.secrets import InMemorySecretStore
from tests.test_local_embedding import requires_assets


def test_default_local_hy_embed_services_share_one_encoder() -> None:
    first = LocalHyEmbedService()
    second = LocalHyEmbedService()

    assert first._embedder is second._embedder  # noqa: SLF001


def test_provider_kind_includes_local_onnx() -> None:
    assert ProviderKind.LOCAL_ONNX.value == "local_onnx"


def test_missing_embedding_defaults_to_the_builtin_model() -> None:
    provider, model, base_url, dimensions = apply_builtin_embedding_defaults(
        embedding_model=None,
        embedding_provider_kind=None,
        embedding_base_url=None,
        embedding_dimensions=None,
    )
    assert provider is ProviderKind.LOCAL_ONNX
    assert model == BUILTIN_EMBEDDING_MODEL
    assert base_url is None
    assert dimensions == BUILTIN_EMBEDDING_DIMENSIONS


def test_an_explicit_embedding_is_left_alone() -> None:
    provider, model, base_url, dimensions = apply_builtin_embedding_defaults(
        embedding_model="text-embedding-3-small",
        embedding_provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        embedding_base_url="https://api.openai.com/v1",
        embedding_dimensions=1536,
    )
    assert provider is ProviderKind.OPENAI_COMPATIBLE
    assert model == "text-embedding-3-small"
    assert base_url == "https://api.openai.com/v1"
    assert dimensions == 1536


def test_creating_a_profile_without_embedding_gets_the_builtin(
    tmp_path: Path,
) -> None:
    store = ModelProfileStore(tmp_path / "profiles.db")
    secrets = InMemorySecretStore()
    profile = store.create(
        ModelProfileInput(
            name="gen-only",
            provider_kind=ProviderKind.OLLAMA,
            model="qwen2.5",
        ),
        secrets,
    )
    assert profile.embedding_provider_kind is ProviderKind.LOCAL_ONNX
    assert profile.embedding_model == BUILTIN_EMBEDDING_MODEL
    assert profile.embedding_dimensions == BUILTIN_EMBEDDING_DIMENSIONS


def test_local_embedding_is_exempt_from_the_shared_origin_rule(
    tmp_path: Path,
) -> None:
    # Remote embedding must share the generation origin and key. Local
    # embedding never leaves the machine, so the same rule would block the
    # exact combination this feature exists for: remote generation + local
    # embedding.
    store = ModelProfileStore(tmp_path / "profiles.db")
    secrets = InMemorySecretStore()
    profile = store.create(
        ModelProfileInput(
            name="mixed",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://api.example.com/v1",
            model="gpt-4o-mini",
            embedding_provider_kind=ProviderKind.LOCAL_ONNX,
            embedding_model=BUILTIN_EMBEDDING_MODEL,
            embedding_dimensions=BUILTIN_EMBEDDING_DIMENSIONS,
            api_key="sk-test",
        ),
        secrets,
    )
    assert profile.embedding_provider_kind is ProviderKind.LOCAL_ONNX


def test_build_config_for_local_embedding_needs_no_embedding_key(
    tmp_path: Path,
) -> None:
    from tests.test_hy_memory_bridge import snapshot

    profile = snapshot(
        ProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.example.com/v1",
        has_api_key=True,
        embedding_provider=ProviderKind.LOCAL_ONNX,
    ).model_copy(
        update={
            "embedding_model": BUILTIN_EMBEDDING_MODEL,
            "embedding_dimensions": BUILTIN_EMBEDDING_DIMENSIONS,
        }
    )
    config = build_hy_memory_config(profile, api_key="sk-gen", data_dir=tmp_path)
    assert config.vector_store.embedding_dims == BUILTIN_EMBEDDING_DIMENSIONS
    assert config.embedder.embedding_dims == BUILTIN_EMBEDDING_DIMENSIONS


@requires_assets
def test_local_hy_embed_service_returns_unit_512_vectors() -> None:
    import asyncio

    service = LocalHyEmbedService(LocalEmbedder())
    vector = asyncio.run(service.embed("本地嵌入不需要出网"))
    assert len(vector) == 512
    length = sum(value * value for value in vector) ** 0.5
    assert length == pytest.approx(1.0, abs=1e-4)


@requires_assets
def test_create_client_swaps_in_the_local_embed_service(tmp_path: Path) -> None:
    from tests.test_hy_memory_bridge import snapshot

    profile = snapshot(
        ProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.example.com/v1",
        has_api_key=True,
        embedding_provider=ProviderKind.LOCAL_ONNX,
    ).model_copy(
        update={
            "embedding_model": BUILTIN_EMBEDDING_MODEL,
            "embedding_dimensions": BUILTIN_EMBEDDING_DIMENSIONS,
        }
    )
    # HyMemoryClient opens local chroma/kuzu on a fresh data_dir and leaves
    # the embedder alone until first call, so this does not reach the network.
    client = create_hy_memory_client(profile, api_key="sk-gen", data_dir=tmp_path)
    try:
        assert isinstance(client._embed_service, LocalHyEmbedService)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def test_local_embed_service_covers_every_method_hy_calls() -> None:
    """我们的替代品必须覆盖 HY 真会调的全部方法 —— 名单从 HY 源码里数，不写死。

    上一版这个类只实现了 `embed`，注释还写着「HY only ever calls .embed on it」。
    装着的这个 HY 版本里，写入流水线调的是 `embed_queued`（17 处）、`embed_batch`
    （12 处）、`embed`（11 处）、`embed_with_meta`（1 处）。缺的那些不会报缺方法，
    而是让 HY 退回它自己那个指向占位地址的服务，于是抽取以连接失败告终、
    一条记忆都产不出来。

    名单是数出来的而不是抄下来的：抄下来的名单会随 HY 升级一起烂掉，
    而这条测试的全部意义就是替我们盯住那次升级。
    """
    import re
    from pathlib import Path as _Path

    import hy_memory

    root = _Path(hy_memory.__file__).parent
    called: set[str] = set()
    for path in root.rglob("*.py"):
        if path.name == "embed_service.py":
            continue
        called.update(re.findall(r"embed_service\.([a-z_]+)", path.read_text(encoding="utf-8")))

    assert called, "一个调用点都没数到，说明这条测试自己坏了"
    missing = {name for name in called if not callable(getattr(LocalHyEmbedService, name, None))}
    assert missing == set(), f"HY 会调但我们没实现：{sorted(missing)}"


@requires_assets
def test_the_pipelines_get_the_local_embed_service_not_only_the_client(
    tmp_path: Path,
) -> None:
    """真正干活的模块拿到的必须也是本地那个。

    这是漏掉的那一步：client 在 __init__ 里把它自己那个 EmbedService 交给了
    组件工厂（client.py:300），而所有流水线都从工厂取（registry.py:103/137/177）。
    只替换 client 上的引用，工厂手里攥着的还是原来那个 —— 指向
    http://127.0.0.1/local-onnx，连 TCP 都建不起来。

    旧测试只断言 client 上那个引用，所以它一直是绿的，而抽取一直是零产出。
    """
    from tests.test_hy_memory_bridge import snapshot

    profile = snapshot(
        ProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.example.com/v1",
        has_api_key=True,
        embedding_provider=ProviderKind.LOCAL_ONNX,
    ).model_copy(
        update={
            "embedding_model": BUILTIN_EMBEDDING_MODEL,
            "embedding_dimensions": BUILTIN_EMBEDDING_DIMENSIONS,
        }
    )
    client = create_hy_memory_client(profile, api_key="sk-gen", data_dir=tmp_path)
    try:
        shared = client._registry._shared_embed_service
        assert isinstance(shared, LocalHyEmbedService)
        # 同一个对象，不是两份各自缓存的替代品：HY 的服务自带批处理队列，
        # 两份会各攒一队，而队列的意义就是同一批一起走。
        assert shared is client._embed_service
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


@requires_assets
def test_the_write_pipeline_itself_gets_the_local_embed_service(tmp_path: Path) -> None:
    """真正写记忆的那条流水线手里必须是本地那个。

    这是前两条守卫都没守住的一层，而它才是决定成败的一层。实测：改完
    client 与工厂两处引用之后，真实导入仍然 67 次 ConnectError、零记忆产出。
    原因是 client.__init__ 在 client.py:332 就把 System2Writer 预热建好了 ——
    那时替换还没发生，于是它抓走了 HY 原本那个服务并传给内层 writer，而
    registry._system2_writer 一旦有值就永不重建。

    调用链是实测出来的，不是读出来的：给真实 EmbedService 的 embed_queued 挂
    栈回溯，它自己报出 client.async_add -> system2_writer.write ->
    writer.write -> embed_queued。
    """
    from tests.test_hy_memory_bridge import snapshot

    profile = snapshot(
        ProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.example.com/v1",
        has_api_key=True,
        embedding_provider=ProviderKind.LOCAL_ONNX,
    ).model_copy(
        update={
            "embedding_model": BUILTIN_EMBEDDING_MODEL,
            "embedding_dimensions": BUILTIN_EMBEDDING_DIMENSIONS,
        }
    )
    client = create_hy_memory_client(profile, api_key="sk-gen", data_dir=tmp_path)
    try:
        writer = asyncio.run(client._registry.get_system2_writer())
        assert isinstance(writer._embed_service, LocalHyEmbedService)
        # 内层 writer 也要 —— 栈回溯显示 embed_queued 是它调的，不是 System2 调的。
        inner = getattr(writer, "_writer", None) or getattr(writer, "writer", None)
        assert inner is not None, "找不到内层 writer，这条测试自己坏了"
        assert isinstance(inner._embed_service, LocalHyEmbedService)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


@requires_assets
def test_named_read_pipeline_uses_local_embedding_after_cache_replacement(tmp_path: Path) -> None:
    from tests.test_hy_memory_bridge import snapshot

    profile = snapshot(
        ProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.example.com/v1",
        has_api_key=True,
        embedding_provider=ProviderKind.LOCAL_ONNX,
    ).model_copy(
        update={
            "embedding_model": BUILTIN_EMBEDDING_MODEL,
            "embedding_dimensions": BUILTIN_EMBEDDING_DIMENSIONS,
        }
    )
    client = create_hy_memory_client(profile, api_key="test-generation-key", data_dir=tmp_path)
    try:
        reader = client._loop_thread.run(client._registry.get_reader(reader_name="legacy"))
        assert isinstance(reader.embed_service, LocalHyEmbedService)
        assert reader.embed_service is client._embed_service
        assert client._registry._readers["legacy"] is reader
    finally:
        client.close()
