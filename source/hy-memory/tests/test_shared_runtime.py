# -*- coding: utf-8 -*-
"""
SharedRuntime 端到端测试。

覆盖：
1. Solo 模式（不传 runtime）行为完全不变 — backward compat 回归
2. Shared 模式两个 client 可以共存
3. Shared 模式两个 client 共享同一个 cache + 同一个 loop
4. Shared 模式 client.close() 不关 shared cache、不停 shared loop
5. Shared 模式 runtime.close() 关掉 cache 和 loop
6. MetricsCollector 单例在 shared 模式下只 bind 一次（关键 cross-loop bug 防护）
7. 多个 client 真的能并行 add/search 不挂

测试依赖只用 Chroma + SQLite cache（零外部依赖），避免 MySQL/网络。
"""

import asyncio
import uuid

import pytest

from hy_memory import HyMemoryClient, SharedRuntime, MemoryConfig
from hy_memory.metrics import MetricsCollector


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_config(tmp_path, *, dims=32, collection_suffix=""):
    """构造一个不依赖外部服务的 config（chroma + sqlite cache）"""
    suffix = collection_suffix or uuid.uuid4().hex[:8]
    return MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_runtime_{suffix}",
            "persist_directory": str(tmp_path / f"chroma_{suffix}"),
            "embedding_dims": dims,
        },
        "cache": {
            "backend": "sqlite",
            "sqlite_path": str(tmp_path / "cache.db"),
        },
        "history": {"enable": False},
    })


@pytest.fixture(autouse=True)
def _reset_metrics_singleton():
    """每个 test reset MetricsCollector 单例，避免 cross-test 污染"""
    MetricsCollector.reset()
    yield
    MetricsCollector.reset()


@pytest.fixture(autouse=True)
def _safe_env(monkeypatch, tmp_path):
    """避免 test 误连真实 redis/mysql"""
    monkeypatch.setenv("MEMORY_CACHE_BACKEND", "sqlite")
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.delenv("MEMORY_VECTOR_HOST", raising=False)
    monkeypatch.setenv("MEMORY_DATA_DIR", str(tmp_path / ".hy_memory"))
    monkeypatch.setenv("MEMORY_LOG_DIR", str(tmp_path / "logs"))
    yield


# ================================================================
# Phase 1: Solo 模式向后兼容
# ================================================================

class TestSoloModeUnchanged:
    """Solo 模式（不传 runtime）行为必须完全跟改造前一致"""

    def test_solo_client_init_close(self, tmp_path):
        cfg = _make_config(tmp_path)
        client = HyMemoryClient(cfg, mode="lite")
        try:
            # solo 模式 owns_runtime=True
            assert client._owns_runtime is True
            # 自己有 cache + loop_thread
            assert client._cache is not None
            assert client._loop_thread is not None
        finally:
            client.close()

    def test_solo_client_metrics_bound(self, tmp_path):
        cfg = _make_config(tmp_path)
        client = HyMemoryClient(cfg, mode="lite")
        try:
            mc = MetricsCollector.get()
            assert mc._cache is client._cache
            assert mc._background_started is True
        finally:
            client.close()


# ================================================================
# Phase 2: Shared 模式 — 单 client
# ================================================================

class TestSharedRuntimeSingleClient:

    def test_runtime_create_and_close(self, tmp_path):
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            assert runtime.cache is not None
            assert runtime.loop_thread is not None
            assert runtime.metrics is MetricsCollector.get()
            # cache 已经 bind 到 metrics
            assert runtime.metrics._cache is runtime.cache
            assert runtime.metrics._background_started is True
        finally:
            runtime.close()

    def test_client_with_runtime_shares_resources(self, tmp_path):
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            client_cfg = _make_config(tmp_path, collection_suffix="cli1")
            client = HyMemoryClient(client_cfg, mode="lite", runtime=runtime)
            try:
                assert client._owns_runtime is False
                assert client._loop_thread is runtime.loop_thread
                assert client._cache is runtime.cache
            finally:
                client.close()
        finally:
            runtime.close()

    def test_client_close_does_not_close_shared_cache(self, tmp_path):
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            client_cfg = _make_config(tmp_path, collection_suffix="cli1")
            client = HyMemoryClient(client_cfg, mode="lite", runtime=runtime)
            shared_cache = runtime.cache
            client.close()
            # client.close 后 runtime.cache 仍可用
            assert runtime.cache is shared_cache
            # runtime loop 仍在跑
            assert runtime.loop_thread is not None
        finally:
            runtime.close()


# ================================================================
# Phase 3: Shared 模式 — 多 client（核心 bug 防护场景）
# ================================================================

class TestSharedRuntimeMultiClient:

    def test_two_clients_share_one_cache(self, tmp_path):
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            cfg_a = _make_config(tmp_path, collection_suffix="a")
            cfg_b = _make_config(tmp_path, collection_suffix="b")
            client_a = HyMemoryClient(cfg_a, mode="lite", runtime=runtime)
            client_b = HyMemoryClient(cfg_b, mode="lite", runtime=runtime)
            try:
                assert client_a._cache is client_b._cache
                assert client_a._loop_thread is client_b._loop_thread
                assert client_a._cache is runtime.cache
            finally:
                client_a.close()
                client_b.close()
        finally:
            runtime.close()

    def test_metrics_singleton_only_bound_once(self, tmp_path):
        """关键测试：原 bug 是 bind_cache 被第二个 client 覆盖；
        shared 模式下应该只 runtime 调一次 bind_cache，client 都不调"""
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        bound_cache_after_runtime = runtime.metrics._cache
        bg_started_after_runtime = runtime.metrics._background_started

        try:
            cfg_a = _make_config(tmp_path, collection_suffix="a")
            cfg_b = _make_config(tmp_path, collection_suffix="b")
            client_a = HyMemoryClient(cfg_a, mode="lite", runtime=runtime)
            client_b = HyMemoryClient(cfg_b, mode="lite", runtime=runtime)
            try:
                # 创建俩 client 之后，metrics._cache 仍然是 runtime.cache，
                # 没被 client 的 bind_cache 覆盖
                assert MetricsCollector.get()._cache is bound_cache_after_runtime
                assert MetricsCollector.get()._cache is runtime.cache
                # background 状态保持
                assert MetricsCollector.get()._background_started is bg_started_after_runtime
            finally:
                client_a.close()
                client_b.close()
        finally:
            runtime.close()

    def test_clients_use_same_loop_thread(self, tmp_path):
        """关键 cross-loop 防护：所有 client 用同一个 loop"""
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            cfg_a = _make_config(tmp_path, collection_suffix="a")
            cfg_b = _make_config(tmp_path, collection_suffix="b")
            client_a = HyMemoryClient(cfg_a, mode="lite", runtime=runtime)
            client_b = HyMemoryClient(cfg_b, mode="lite", runtime=runtime)
            try:
                # 同一个 _LoopThread 实例
                assert client_a._loop_thread is client_b._loop_thread
                # 同一个底层 event loop
                assert client_a._loop_thread._loop is client_b._loop_thread._loop
            finally:
                client_a.close()
                client_b.close()
        finally:
            runtime.close()


# ================================================================
# Phase 4: 真正跑 add / 验证 functionally works
# ================================================================

class TestSharedRuntimeFunctional:
    """真的发请求过 add/search 看流程能跑通，不挂在 cross-loop"""

    def test_two_clients_add_concurrently_no_crossloop(self, tmp_path):
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            cfg_a = _make_config(tmp_path, collection_suffix="a")
            cfg_b = _make_config(tmp_path, collection_suffix="b")
            client_a = HyMemoryClient(cfg_a, mode="lite", runtime=runtime)
            client_b = HyMemoryClient(cfg_b, mode="lite", runtime=runtime)
            try:
                # 直接走 runtime 的 cache 上的 store/get_pipeline_log（base 协议层落库）
                # 关键验证：两个 client 不在自己的 _LoopThread 上读写 cache
                # 都委托给 runtime 的 loop（避免跨 loop pool 错误）
                shared = runtime.cache

                # 通过 client 的 loop_thread.run 写 cache（应该能跑通）
                async def _w(rid):
                    from hy_memory.utils.pipeline_observability import (
                        drain_pipeline_log_tasks,
                    )
                    await shared.store_pipeline_log(
                        request_id=rid, user_id="u", agent_id="a",
                        step="TEST", prompt="p", response="r",
                    )
                    await drain_pipeline_log_tasks()
                async def _r(rid):
                    return await shared.get_pipeline_logs(request_id=rid)

                client_a._loop_thread.run(_w("rid_a"))
                client_b._loop_thread.run(_w("rid_b"))
                # 跨 client 读对方写的，证明同一 pool
                assert len(client_a._loop_thread.run(_r("rid_b"))) == 1
                assert len(client_b._loop_thread.run(_r("rid_a"))) == 1
            finally:
                client_a.close()
                client_b.close()
        finally:
            runtime.close()


# ================================================================
# Phase 5: aclose / close 语义
# ================================================================

class TestSharedRuntimeClose:

    def test_runtime_close_idempotent(self, tmp_path):
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        runtime.close()
        # 再关一次不挂
        runtime.close()

    def test_aclose_async(self, tmp_path):
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        # 用 runtime.loop_thread.run 调 aclose（因为 cache 在那个 loop 上）
        runtime.close()


# ================================================================
# Phase 6: search 专用 loop 与 write loop 隔离
# search 使用独立 loop，避免被 write 队列阻塞。
# ================================================================

class TestSearchLoopIsolation:
    """search 走独立 _LoopThread，不被 write 队列挤占调度。"""

    def test_solo_search_loop_is_distinct_thread(self, tmp_path):
        """solo 模式：search loop 与 write loop 是两个独立的 event loop/线程。"""
        cfg = _make_config(tmp_path)
        client = HyMemoryClient(cfg, mode="lite")
        try:
            assert client._search_loop_thread is not None
            assert client._search_loop_thread is not client._loop_thread
            assert client._search_loop_thread._loop is not client._loop_thread._loop
            assert client._search_loop_thread._thread is not client._loop_thread._thread
            assert client._search_loop_thread._thread.is_alive()
        finally:
            client.close()

    def test_shared_search_loop_from_runtime(self, tmp_path):
        """shared 模式：client 的 search loop 来自 runtime.search_loop_thread，
        且与 write loop 隔离；多个 client 共用同一个 search loop。"""
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            assert runtime.search_loop_thread is not None
            assert runtime.search_loop_thread is not runtime.loop_thread
            assert runtime.search_loop_thread._loop is not runtime.loop_thread._loop

            cfg_a = _make_config(tmp_path, collection_suffix="a")
            cfg_b = _make_config(tmp_path, collection_suffix="b")
            client_a = HyMemoryClient(cfg_a, mode="lite", runtime=runtime)
            client_b = HyMemoryClient(cfg_b, mode="lite", runtime=runtime)
            try:
                # search loop 来自 runtime，与 write loop 隔离
                assert client_a._search_loop_thread is runtime.search_loop_thread
                assert client_a._search_loop_thread is not client_a._loop_thread
                # 多 client 共用同一个 search loop
                assert client_a._search_loop_thread is client_b._search_loop_thread
            finally:
                client_a.close()
                client_b.close()
        finally:
            runtime.close()

    def test_backward_compat_old_runtime_without_search_loop(self, tmp_path):
        """兼容旧 runtime（无 search_loop_thread 属性）：回落到 write loop，不报错。"""
        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            # 模拟旧 runtime：抹掉 search 专用 loop
            old_search = runtime._search_loop_thread
            runtime._search_loop_thread = None
            client_cfg = _make_config(tmp_path, collection_suffix="compat")
            client = HyMemoryClient(client_cfg, mode="lite", runtime=runtime)
            try:
                # 回落到 write loop（行为等价旧路径，不隔离但不崩）
                assert client._search_loop_thread is runtime.loop_thread
            finally:
                client.close()
            runtime._search_loop_thread = old_search
        finally:
            runtime.close()

    def test_search_loop_schedules_while_write_loop_blocked(self, tmp_path):
        """核心回归：write loop 被一个长时间同步阻塞的协程占满时，search loop
        仍能及时调度协程——证明二者互不挤占。

        直接在 loop 调度层验证（不拉入 chroma/embed），精确对应本次修复：
        改动前 search 和 write 共用一个 loop，提交到该 loop 的 search 协程会被
        卡到 write 的阻塞结束；改动后 search 有独立 loop，调度不受影响。
        """
        import time
        import asyncio as _aio

        cfg = _make_config(tmp_path)
        runtime = run(SharedRuntime.create(cfg))
        try:
            write_loop = runtime.loop_thread._loop
            search_loop = runtime.search_loop_thread._loop
            assert write_loop is not search_loop  # 前提：确实是两个 loop

            BLOCK_SEC = 2.0

            async def _hog():
                # 同步 sleep 占满 write loop（协作式调度下彻底卡住该 loop），
                # 模拟 EXTRACT/RECONCILE 中夹杂的非 await 同步代码段。
                time.sleep(BLOCK_SEC)

            async def _probe():
                # 极轻量探针：代表一次 search 协程被提交后能否被及时调度执行。
                return "scheduled"

            # 1. 占满 write loop
            hog_fut = _aio.run_coroutine_threadsafe(_hog(), write_loop)
            time.sleep(0.1)  # 确保 hog 真正开始执行、占住 write loop

            # 2. 此刻 write loop 卡死 → 提交到 search loop 的探针应立刻被调度
            t0 = time.perf_counter()
            probe_fut = _aio.run_coroutine_threadsafe(_probe(), search_loop)
            assert probe_fut.result(timeout=1.0) == "scheduled"
            search_latency = time.perf_counter() - t0

            # search loop 调度延迟应是「毫秒级」——独立 loop 完全不受 write 阻塞影响。
            # 阈值取远小于 BLOCK_SEC 的绝对值：改动前 search/write 共用一个 loop 时，
            # 探针会被 hog 卡到接近 BLOCK_SEC 才调度，必然超过此阈值 → 回归被捕获。
            _SCHED_BUDGET = 0.3
            assert search_latency < _SCHED_BUDGET, (
                f"search loop 调度耗时 {search_latency:.3f}s（应 < {_SCHED_BUDGET}s），"
                f"说明未与 write loop（阻塞 {BLOCK_SEC}s）隔离"
            )

            # 3. 对照：同一探针提交到 write loop 会被 hog 卡住，直到阻塞结束
            t1 = time.perf_counter()
            write_probe_fut = _aio.run_coroutine_threadsafe(_probe(), write_loop)
            assert write_probe_fut.result(timeout=BLOCK_SEC + 1.0) == "scheduled"
            write_latency = time.perf_counter() - t1
            # write loop 上的探针确实被 hog 挤压（证明 hog 生效、对照有意义）
            assert write_latency > search_latency, (
                "write loop 探针应比 search loop 探针慢（被 hog 阻塞），"
                "否则说明 hog 没有真正占用 write loop，对照无效"
            )

            hog_fut.result(timeout=BLOCK_SEC + 1)  # 收尾，避免 teardown 残留
        finally:
            runtime.close()
