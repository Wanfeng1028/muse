# -*- coding: utf-8 -*-
"""embed 攒批队列：HTTP 必须在 _queue_lock 之外执行。

回归背景（线上事故 2026-08-20）：
早期 `_flush_queue` 在持有 `_queue_lock` 的同时 await HTTP。由于
`_embed_texts_with_meta` 是逐条发请求的，一批 8 条 × ~1.7s ≈ 13.5s 全程持锁，
后续 `embed_queued` 全堵在入队处的 `async with self._queue_lock` 上。
线上实测单条 embed 的 `lock_wait_ms` 达 34.7s、`S1_EMBED` step 报 48s，
而真实 HTTP 仅 1.78s —— 报警误判为"Embed 超时"。

修复：锁内只做内存操作（入队 / `_detach_batch`），`_send_batch` 在锁外调用。
本测试固化该契约，防止回退。
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.core.embed_service import EmbedService


HTTP_MS = 0.05  # 单条 HTTP 模拟耗时（真实 ~1.7s，等比缩小以便快速测试）


def _make_service(*, batch_size: int = 8, window_ms: float = 1000.0) -> EmbedService:
    cfg = MemoryConfig.from_env()
    cfg.embedder.base_url = "http://fake/v1"
    cfg.embedder.api_key = "K"
    cfg.embedder.embedding_dims = None
    svc = EmbedService(cfg)
    svc._embed_config.queue_batch_size = batch_size
    svc._embed_config.queue_batch_window_ms = window_ms
    svc._embed_config.enable_cache = False  # 强制每条都进队列
    return svc


class _FakeRaw:
    """模拟 provider 响应：按 input 条数返回同样多的向量，并带 index。

    真实 OpenAI embedding 协议下 data 每项带 index（对应 input 下标），
    条数与 input 一致。这里刻意把 index 逆序放，用来验证 SDK 按 index 排序
    而不是依赖 data 的物理顺序。
    """

    status_code = 200
    headers: dict = {}

    def __init__(self, input_count: int = 1):
        self._input_count = max(1, input_count)

    def parse(self):
        resp = MagicMock()
        items = []
        for i in range(self._input_count):
            item = MagicMock()
            # 第 i 条的向量首元素 = i，便于断言顺序正确
            item.embedding = [float(i), 0.1, 0.2, 0.3]
            item.index = i
            items.append(item)
        resp.data = list(reversed(items))   # 故意乱序，考验按 index 排序
        resp.model = "fake-model"
        resp.usage = None
        return resp


def _slow_client_factory(**_kwargs):
    """embeddings.create 睡 HTTP_MS 秒，模拟一次批量请求的网络往返。"""

    class _Embeddings:
        class with_raw_response:
            @staticmethod
            async def create(**kwargs):
                await asyncio.sleep(HTTP_MS)
                texts = kwargs.get("input") or []
                return _FakeRaw(input_count=len(texts) if isinstance(texts, list) else 1)

    client = MagicMock()
    client.embeddings = _Embeddings()
    return client


class TestEmbedQueueLockNotHeldDuringHttp:
    """锁不得覆盖 HTTP：并发写入的 lock_wait_ms 必须远小于一批 HTTP 耗时。"""

    @pytest.mark.asyncio
    async def test_lock_wait_far_below_batch_http_time(self):
        batch_size = 8
        svc = _make_service(batch_size=batch_size)
        n = batch_size * 2  # 两批

        with patch("openai.AsyncOpenAI", side_effect=_slow_client_factory):
            results = await asyncio.gather(
                *[svc.embed_queued_with_meta(f"text-{i}") for i in range(n)]
            )

        assert len(results) == n
        assert all(len(vec) == 4 for vec, _ in results)

        lock_waits = [meta["lock_wait_ms"] for _, meta in results]
        one_batch_http_ms = HTTP_MS * 1000 * batch_size

        # 若 HTTP 仍在锁内，后来者的 lock_wait 会逼近一整批的 HTTP 耗时。
        assert max(lock_waits) < one_batch_http_ms * 0.25, (
            f"lock_wait_ms max={max(lock_waits):.1f} 接近一批 HTTP "
            f"{one_batch_http_ms:.0f}ms —— HTTP 可能又被放回锁内"
        )

    @pytest.mark.asyncio
    async def test_detach_batch_is_pure_memory_op(self):
        """_detach_batch 必须是同步函数（不含 await），保证锁内无 I/O。"""
        svc = _make_service()
        assert not asyncio.iscoroutinefunction(svc._detach_batch)

        bucket = ("http://fake/v1", "K")
        svc._queue_pending[bucket] = [("a", MagicMock(), 0.0, 0.0, 1)]
        batch = svc._detach_batch(bucket)
        assert batch is not None and len(batch) == 1
        assert svc._queue_pending[bucket] == []       # 摘走后应清空
        assert svc._detach_batch(bucket) is None      # 空队列返回 None
        assert svc._detach_batch(("other", "x")) is None  # 未知桶也安全


class TestEmbedQueueBehaviourPreserved:
    """修复不得破坏原有攒批语义。"""

    @pytest.mark.asyncio
    async def test_timer_flush_still_works_when_batch_not_full(self):
        """攒不满 batch_size 时，定时 flush 仍须兜底（否则请求永久挂起）。"""
        window_ms = 200.0
        svc = _make_service(batch_size=8, window_ms=window_ms)

        started = time.perf_counter()
        with patch("openai.AsyncOpenAI", side_effect=_slow_client_factory):
            results = await asyncio.wait_for(
                asyncio.gather(*[svc.embed_queued_with_meta(f"t{i}") for i in range(3)]),
                timeout=5.0,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000

        assert all(len(vec) == 4 for vec, _ in results)
        assert results[0][1]["batch_size"] == 3      # 按实际条数成批
        assert elapsed_ms >= window_ms * 0.8         # 确实等过定时窗口

    @pytest.mark.asyncio
    async def test_http_failure_propagates_to_all_futures(self):
        """一批失败时所有 future 都要收到异常，不能悬挂（否则 write 卡死）。"""
        batch_size = 4
        svc = _make_service(batch_size=batch_size, window_ms=200.0)

        def _failing_client(**_kwargs):
            class _Embeddings:
                class with_raw_response:
                    @staticmethod
                    async def create(**_k):
                        raise ValueError("boom")

            client = MagicMock()
            client.embeddings = _Embeddings()
            return client

        with patch("openai.AsyncOpenAI", side_effect=_failing_client):
            results = await asyncio.gather(
                *[svc.embed_queued_with_meta(f"bad-{i}") for i in range(batch_size)],
                return_exceptions=True,
            )

        assert len(results) == batch_size
        assert all(isinstance(r, Exception) for r in results)

    @pytest.mark.asyncio
    async def test_queue_diagnostics_fields_present(self):
        """provider_meta 仍须带齐队列诊断字段（线上定位依赖它们）。"""
        svc = _make_service(batch_size=2, window_ms=200.0)

        with patch("openai.AsyncOpenAI", side_effect=_slow_client_factory):
            (_vec, meta), _ = await asyncio.gather(
                svc.embed_queued_with_meta("x1"),
                svc.embed_queued_with_meta("x2"),
            )

        for key in (
            "batch_size",
            "position_in_batch",
            "queue_depth",
            "queue_wait_ms",
            "lock_wait_ms",
            "batch_flush_ms",
            "queue_batch_size_config",
            "queue_batch_window_ms",
            "embed_request_ms",
        ):
            assert key in meta, f"provider_meta 缺少诊断字段 {key}"
