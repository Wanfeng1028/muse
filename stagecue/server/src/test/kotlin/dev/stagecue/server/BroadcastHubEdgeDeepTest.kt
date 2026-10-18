package dev.stagecue.server

import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.server.ws.BroadcastHub
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class BroadcastHubEdgeDeepTest {

    // 辅助：构造一个在外部 scope 中注册的 sink，将收到的消息推入 Channel 便于断言。
    private fun CoroutineScope.collectingSink(ch: Channel<String>): BroadcastHub.FrameSink =
        BroadcastHub.FrameSink { text -> ch.send(text) }

    // 轮询等待直到条件满足或超时（最多 2 秒），用 delay 而非 Thread.sleep。
    private suspend fun awaitUntil(timeoutMs: Long = 2_000, condition: () -> Boolean): Boolean =
        withTimeoutOrNull(timeoutMs) {
            while (!condition()) {
                delay(10)
            }
            true
        } ?: false

    @Test
    fun `broadcast to empty hub does not throw`() = runBlocking {
        // 推导：没有任何客户端注册时，slots 为空，broadcastExcept 内部 for 循环体不执行。
        // 应安全返回，不抛异常。
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics)
        hub.broadcastExcept(null, "x")
        assertEquals(0, hub.sessionCount())
    }

    @Test
    fun `broadcastExcept null delivers to all`() = runBlocking {
        // 推导：exceptClientId 为 null 时，`if (id == exceptClientId) continue` 永远不触发，
        // 所有已注册 slot 都应收到消息。用两个独立 Channel 收集各自 sink 的接收内容。
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val aCh = Channel<String>(Channel.UNLIMITED)
            val bCh = Channel<String>(Channel.UNLIMITED)
            hub.register("a", scope.collectingSink(aCh), scope)
            hub.register("b", scope.collectingSink(bCh), scope)

            hub.broadcastExcept(null, "hello")

            val aGot = withTimeoutOrNull(2_000) { aCh.receive() }
            val bGot = withTimeoutOrNull(2_000) { bCh.receive() }
            assertEquals("hello", aGot)
            assertEquals("hello", bGot)
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun `sessionCount tracks register and unregister`() = runBlocking {
        // 推导：sessionCount() 直接返回 slots.size。注册/注销应实时反映。
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            assertEquals(0, hub.sessionCount())

            val aCh = Channel<String>(Channel.UNLIMITED)
            hub.register("a", scope.collectingSink(aCh), scope)
            assertEquals(1, hub.sessionCount())

            val bCh = Channel<String>(Channel.UNLIMITED)
            hub.register("b", scope.collectingSink(bCh), scope)
            assertEquals(2, hub.sessionCount())

            hub.unregister("a")
            // unregister 立即从 slots 中移除，size 同步下降。
            assertEquals(1, hub.sessionCount())
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun `unregister unknown id is no-op`() = runBlocking {
        // 推导：unregister 中 `slots.remove(clientId) ?: return`，未知 id 直接返回。
        // sessionCount 保持不变，且不抛异常。
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val aCh = Channel<String>(Channel.UNLIMITED)
            hub.register("a", scope.collectingSink(aCh), scope)
            val before = hub.sessionCount()

            hub.unregister("ghost")

            assertEquals(before, hub.sessionCount())
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun `register returns active job`() = runBlocking {
        // 推导：register 内部 launch 一个协程处理 slot.channel，直到 unregister 或 sink 失败。
        // 未注销前该 Job 应保持 isActive。
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val aCh = Channel<String>(Channel.UNLIMITED)
            val job: Job = hub.register("a", scope.collectingSink(aCh), scope)

            assertTrue(job.isActive, "register 返回的 Job 在未取消前应处于 active 状态")
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun `unregister cancels the job`() = runBlocking {
        // 推导：unregister 会调用 slot.job?.cancel()。取消后 Job 状态最终变为 cancelled。
        // 用轮询等待（delay）避免竞态，最多 2 秒。
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val aCh = Channel<String>(Channel.UNLIMITED)
            val job: Job = hub.register("a", scope.collectingSink(aCh), scope)

            hub.unregister("a")

            val cancelled = awaitUntil { job.isCancelled }
            assertTrue(cancelled, "unregister 后 Job 应最终进入 cancelled 状态")
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun `re-register replaces sink`() = runBlocking<Unit> {
        // 推导：register 首先调用 unregister(clientId) 移除旧 slot，再放入新 slot。
        // 因此同一 clientId 二次注册后，广播只应到达新 sink。
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val aCh = Channel<String>(Channel.UNLIMITED)
            hub.register("a", scope.collectingSink(aCh), scope)

            val bCh = Channel<String>(Channel.UNLIMITED)
            hub.register("a", scope.collectingSink(bCh), scope)

            hub.broadcastExcept(null, "x")

            val bGot = withTimeoutOrNull(2_000) { bCh.receive() }
            assertEquals("x", bGot)

            // 旧 sink 不应收到任何消息（旧 channel 已随旧 slot 一起被丢弃/关闭）。
            val aGot = withTimeoutOrNull(200) { aCh.receive() }
            assertNull(aGot, "旧 sink 不应再收到消息")
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun `broadcastExcept excludes only the named client`() = runBlocking<Unit> {
        // 推导：exceptClientId 为 "b" 时，只有 id == "b" 的 slot 被 continue 跳过。
        // a、c 应收到，b 收不到。
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val aCh = Channel<String>(Channel.UNLIMITED)
            val bCh = Channel<String>(Channel.UNLIMITED)
            val cCh = Channel<String>(Channel.UNLIMITED)
            hub.register("a", scope.collectingSink(aCh), scope)
            hub.register("b", scope.collectingSink(bCh), scope)
            hub.register("c", scope.collectingSink(cCh), scope)

            hub.broadcastExcept("b", "x")

            val aGot = withTimeoutOrNull(2_000) { aCh.receive() }
            val cGot = withTimeoutOrNull(2_000) { cCh.receive() }
            assertEquals("x", aGot)
            assertEquals("x", cGot)

            val bGot = withTimeoutOrNull(200) { bCh.receive() }
            assertNull(bGot, "被排除的 b 不应收到消息")
        } finally {
            scope.cancel()
        }
    }
}
