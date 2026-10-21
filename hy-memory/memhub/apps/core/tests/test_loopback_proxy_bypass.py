"""环回地址不得走 HTTP(S)_PROXY。

Some environments set a system HTTP proxy; httpx defaults to trust_env=True and may send
127.0.0.1 / localhost / ::1 的请求交给代理，表现成「本地 Ollama
连不上 / health 起不来」，排查会被带偏。远端 HTTPS 服务仍须走代理。

判据是**传输层归属**而不是「假代理有没有收到连接」：后者链路太长，
任何一环没起来都会静默变成「没被劫持」，于是正向对照失效而无人发现。
这里直接问 client 某个 URL 会走哪个连接池、那个池有没有代理。

本文件不靠设置 NO_PROXY 变绿——那是环境绕过，不是产品修复。
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from one_memory.http_client import create_async_client, create_client

# 企业代理的替身。只做归属判定，不会真的发起连接，所以不需要它活着。
FAKE_PROXY = "http://127.0.0.1:9"

LOOPBACK_URLS = (
    "http://127.0.0.1:8791/api/v1/health",
    "http://localhost:11434/api/tags",
    "http://[::1]:11434/api/tags",
)
REMOTE_URLS = (
    "https://models.example.com/v1/chat/completions",
    "https://generation.example.net/v1/chat/completions",
)


def _origin(url: object) -> str:
    """把 httpcore.URL 与 httpx.URL 都归一成 `scheme://host:port`。"""
    scheme = getattr(url, "scheme", b"")
    host = getattr(url, "host", b"")
    port = getattr(url, "port", None)
    if isinstance(scheme, bytes):
        scheme = scheme.decode()
    if isinstance(host, bytes):
        host = host.decode()
    return f"{scheme}://{host}:{port}"


def proxy_for(client: httpx.Client | httpx.AsyncClient, url: str) -> str | None:
    """返回 httpx 为该 URL 选中的代理（`scheme://host:port`），直连时返回 None。

    依赖 httpx 0.28.x 的内部结构（`_transport_for_url` 与 `pool._proxy_url`）。
    结构变了就在这里失败，而不是让所有断言静默变成「直连」。
    池上的 `_proxy_url` 是 httpcore.URL（字段是 bytes），不能直接和 httpx.URL 比。
    """
    transport = client._transport_for_url(httpx.URL(url))
    pool = getattr(transport, "_pool", None)
    assert pool is not None, (
        f"httpx transport {type(transport).__name__} 没有 _pool，内部结构已变，本文件的判据需要重写"
    )
    known_pool = type(pool).__name__ in {
        "ConnectionPool",
        "AsyncConnectionPool",
        "HTTPProxy",
        "AsyncHTTPProxy",
    }
    assert known_pool, (
        f"未知的连接池类型 {type(pool).__name__}，无法判断代理归属；"
        "httpx 版本变了，请重写本文件的判据"
    )
    proxy = getattr(pool, "_proxy_url", None)
    return None if proxy is None else _origin(proxy)


@pytest.fixture
def env_proxy(monkeypatch: pytest.MonkeyPatch) -> str:
    # 必须先清掉环境里**所有** *_proxy 变量，再设假代理。
    # 只 setenv 大写的 HTTP_PROXY 是不够的：urllib 的 getproxies_environment()
    # 会把变量名统一小写后收集，机器上若已有小写 http_proxy（企业代理常这么设），
    # 它会盖掉这里设的假代理，于是正向对照断言拿到的是真实代理地址而非 FAKE_PROXY，
    # 三条测试在「设了小写代理的机器上」必红、在没设的机器上全绿 —— 结果取决于环境。
    for name in list(os.environ):
        if name.lower().endswith("_proxy"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", FAKE_PROXY)
    monkeypatch.setenv("HTTPS_PROXY", FAKE_PROXY)
    return FAKE_PROXY


def test_plain_httpx_sends_loopback_through_env_proxy(env_proxy: str) -> None:
    """正向对照：不修的话环回真的会被代理劫走，负向断言才有意义。"""
    expected = _origin(httpx.URL(env_proxy))
    with httpx.Client() as client:
        hijacked = {url: proxy_for(client, url) for url in LOOPBACK_URLS}
    assert all(proxy == expected for proxy in hijacked.values()), (
        f"env proxy 没有劫持环回，正向对照失效：{hijacked}"
    )


def test_create_client_keeps_loopback_direct_while_http_proxy_is_set(
    env_proxy: str,
) -> None:
    del env_proxy
    with create_client() as client:
        routed = {url: proxy_for(client, url) for url in LOOPBACK_URLS}
    assert all(proxy is None for proxy in routed.values()), f"环回仍在走代理：{routed}"


def test_create_async_client_keeps_loopback_direct_while_http_proxy_is_set(
    env_proxy: str,
) -> None:
    del env_proxy

    async def routes() -> dict[str, str | None]:
        async with create_async_client() as client:
            return {url: proxy_for(client, url) for url in LOOPBACK_URLS}

    routed = asyncio.run(routes())
    assert all(proxy is None for proxy in routed.values()), f"环回仍在走代理：{routed}"


def test_remote_requests_still_use_env_proxy(env_proxy: str) -> None:
    """Only loopback bypasses the proxy; remote HTTPS still uses it."""
    expected = _origin(httpx.URL(env_proxy))
    with create_client() as client:
        sync_routed = {url: proxy_for(client, url) for url in REMOTE_URLS}

    async def routes() -> dict[str, str | None]:
        async with create_async_client() as client:
            return {url: proxy_for(client, url) for url in REMOTE_URLS}

    async_routed = asyncio.run(routes())
    assert all(proxy == expected for proxy in sync_routed.values()), (
        f"远端 HTTPS 绕过了代理：{sync_routed}"
    )
    assert all(proxy == expected for proxy in async_routed.values()), (
        f"远端 HTTPS 绕过了代理：{async_routed}"
    )


def test_injected_transport_is_not_shadowed_by_the_mounts(env_proxy: str) -> None:
    """调用方传 transport= 时不得被环回挂载盖掉，否则 MockTransport 会被打穿。"""
    del env_proxy
    mock = httpx.MockTransport(lambda _request: httpx.Response(200))
    with create_client(transport=mock) as client:
        for url in (*LOOPBACK_URLS, *REMOTE_URLS):
            assert client._transport_for_url(httpx.URL(url)) is mock


def test_removing_loopback_mounts_lets_the_proxy_take_loopback_back(
    env_proxy: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """变异：去掉环回直连挂载后，环回必须重新落到代理上。"""
    import one_memory.http_client as http_client

    monkeypatch.setattr(http_client, "LOOPBACK_DIRECT_MOUNTS", {})
    expected = _origin(httpx.URL(env_proxy))
    with create_client() as client:
        routed = {url: proxy_for(client, url) for url in LOOPBACK_URLS}
    assert all(proxy == expected for proxy in routed.values()), (
        f"去掉挂载后环回仍是直连，说明守卫守的不是挂载：{routed}"
    )
