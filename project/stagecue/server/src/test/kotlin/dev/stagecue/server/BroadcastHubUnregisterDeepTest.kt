package dev.stagecue.server

import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.server.ws.BroadcastHub
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * BroadcastHub 生命周期语义测试：
 * - unregister 幂等（重复/不存在不抛异常、不改变 sessionCount）
 * - unregister 后同 id 可重新注册并正常收消息
 * - register 返回的 Job 在 unregister 后被取消
 * - scope 取消触发 finally 清理 slots
 * - 大量注册注销循环无泄漏
 *
 * 并发时序一律用 CompletableDeferred 门闩 + withTimeout 控制，禁止 Thread.sleep 猜时序。
 */
class BroadcastHubUnregisterDeepTest {

    /** 构造被测 hub，使用固定容量，避免依赖默认值。 */
    private fun newHub(capacity: Int = 64): Pair<StageMetrics, BroadcastHub> {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, capacity)
        return metrics to hub
    }

    /**
     * 等待 received 集合大小稳定到 expectedSize，或超时失败。
     * 用 CompletableDeferred 无法直接表达"等外部可变集合"，因此这里轮询
     * 但每次让出调度器（delay），且整体受 withTimeout 保护，属于确定性收敛等待。
     */
    private suspend fun drainUntilStable(received: MutableList<String>, expectedSize: Int) {
        withTimeout(5_000) {
            while (received.size < expectedSize) {
                delay(1)
            }
        }
    }

    // 1. 双重 unregister 不抛异常，sessionCount 不变。
    @Test
    fun `双重注销不抛异常且不改变会话数`() = runBlocking {
        val (_, hub) = newHub()
        val received = java.util.Collections.synchronizedList(mutableListOf<String>())
        val started = CompletableDeferred<Unit>()

        hub.register("A", BroadcastHub.FrameSink { text ->
            received.add(text)
            started.complete(Unit)
        }, this)

        assertEquals(1, hub.sessionCount())

        hub.unregister("A")
        assertEquals(0, hub.sessionCount())

        // 第二次注销：幂等，不抛异常，计数保持 0。
        hub.unregister("A")
        assertEquals(0, hub.sessionCount())

        // 再次注销第三个不存在的 id 也不抛异常。
        hub.unregister("never-registered")
        assertEquals(0, hub.sessionCount())
    }

    // 2. unregister 未注册过的 id 不抛异常（独立场景，覆盖空映射路径）。
    @Test
    fun `注销未注册的客户端不抛异常`() = runBlocking {
        val (_, hub) = newHub()
        assertEquals(0, hub.sessionCount())

        hub.unregister("ghost-1")
        hub.unregister("ghost-2")
        assertEquals(0, hub.sessionCount())
    }

    // 3. unregister 后该 clientId 可重新注册并正常收消息。
    @Test
    fun `注销后重新注册可正常收消息`() = runBlocking {
        val (_, hub) = newHub()
        val firstReceived = java.util.Collections.synchronizedList(mutableListOf<String>())
        val secondReceived = java.util.Collections.synchronizedList(mutableListOf<String>())

        // 第一次注册并确认能收到。
        hub.register("A", BroadcastHub.FrameSink { text -> firstReceived.add(text) }, this)
        hub.broadcastExcept(null, "first")
        drainUntilStable(firstReceived, 1)
        assertEquals(listOf("first"), firstReceived.toList())

        // 注销后重新注册，同一个 id 复用。
        hub.unregister("A")
        assertEquals(0, hub.sessionCount())

        hub.register("A", BroadcastHub.FrameSink { text -> secondReceived.add(text) }, this)
        assertEquals(1, hub.sessionCount())

        hub.broadcastExcept(null, "second")
        drainUntilStable(secondReceived, 1)

        // 新 sink 收到新消息；旧 sink 不应再收到。
        assertEquals(listOf("second"), secondReceived.toList())
        assertEquals(listOf("first"), firstReceived.toList())
    }

    // 4. register 返回的 Job：unregister 后 job 已取消（isCancelled）。
    @Test
    fun `注销后注册返回的Job被取消`() = runBlocking {
        val (_, hub) = newHub()
        val received = java.util.Collections.synchronizedList(mutableListOf<String>())

        val job = hub.register("A", BroadcastHub.FrameSink { text -> received.add(text) }, this)
        assertFalse(job.isCancelled)

        hub.unregister("A")
        assertTrue(job.isCancelled)
    }

    // 5. scope 取消后 slots 被清理（finally 分支）：注册后取消 scope，sessionCount 归 0。
    @Test
    fun `作用域取消后会话槽被清理`() = runBlocking {
        val (_, hub) = newHub()
        val received = java.util.Collections.synchronizedList(mutableListOf<String>())
        val sinkEntered = CompletableDeferred<Unit>()

        // 用独立子作用域，便于手动取消。
        val childScope = CoroutineScope(coroutineContext)
        hub.register("A", BroadcastHub.FrameSink { text ->
            received.add(text)
            sinkEntered.complete(Unit)
        }, childScope)
        assertEquals(1, hub.sessionCount())

        // 触发一次投递，确认发送协程确实在跑（降低"根本没启动就清理"的假阳性）。
        hub.broadcastExcept(null, "hello")
        drainUntilStable(received, 1)
        withTimeout(5_000) { sinkEntered.await() }

        // 取消作用域：发送协程被取消，finally 分支应移除 slots 映射。
        childScope.cancel()

        withTimeout(5_000) {
            while (hub.sessionCount() != 0) {
                delay(1)
            }
        }
        assertEquals(0, hub.sessionCount())
    }

    // 6. 大量注册注销循环 200 次后无泄漏：sessionCount 归零且广播正常。
    @Test
    fun `大量注册注销循环后无泄漏`() = runBlocking {
        val (_, hub) = newHub()

        repeat(200) { i ->
            val id = "client-$i"
            val received = java.util.Collections.synchronizedList(mutableListOf<String>())
            val job = hub.register(id, BroadcastHub.FrameSink { text -> received.add(text) }, this)
            assertEquals(1, hub.sessionCount())

            hub.broadcastExcept(null, "msg-$i")
            drainUntilStable(received, 1)
            assertEquals(listOf("msg-$i"), received.toList())

            hub.unregister(id)
            assertTrue(job.isCancelled)
            assertEquals(0, hub.sessionCount())
        }

        // 循环结束后映射已清空。
        assertEquals(0, hub.sessionCount())

        // 广播仍正常：注册一个新客户端能收到消息，说明 hub 未处于损坏状态。
        val finalReceived = java.util.Collections.synchronizedList(mutableListOf<String>())
        hub.register("final", BroadcastHub.FrameSink { text -> finalReceived.add(text) }, this)
        assertEquals(1, hub.sessionCount())
        hub.broadcastExcept(null, "done")
        drainUntilStable(finalReceived, 1)
        assertEquals(listOf("done"), finalReceived.toList())

        hub.unregister("final")
        assertEquals(0, hub.sessionCount())
    }
}