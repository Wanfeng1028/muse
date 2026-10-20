package dev.stagecue.server

import dev.stagecue.server.ws.BroadcastHub

import dev.stagecue.server.metrics.StageMetrics
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.util.Collections

/**
 * BroadcastHub 重复注册 / 注销语义测试。
 *
 * 覆盖点：
 *  - 同 clientId 重复 register 会先 unregister 旧的（幂等），旧 sink 不再收新消息。
 *  - Slot 重建后 seq 归零重新计数，旧队列积压不泄漏到新 sink。
 *  - unregister 幂等（不存在的 id 无异常），注销后不再投递、sessionCount 递减。
 *  - sink 抛异常时自动 unregister。
 *  - 批量注册/注销后 sessionCount 归零，无泄漏。
 *
 * 时序控制：所有等待都用 CompletableDeferred / 轮询 + withTimeout，不使用 Thread.sleep。
 */
class BroadcastHubReRegisterDeepTest {

    // ---------------------------------------------------------------------
    // 辅助工具
    // ---------------------------------------------------------------------

    /** 从 metrics.scrape() 中提取 stagecue_ws_broadcast_dropped_total 的当前值。 */
    private fun droppedTotal(metrics: StageMetrics): Double {
        val text = metrics.scrape()
        val regex = Regex("stagecue_ws_broadcast_dropped_total\\s+([0-9.eE+-]+)")
        val match = regex.find(text) ?: return 0.0
        return match.groupValues[1].toDouble()
    }

    /**
     * 轮询等待 received 集合大小稳定在 expectedSize（且不再变化），带超时。
     * 用轮询而非 sleep 猜时序；收敛后立即返回。
     */
    private suspend fun drainUntilStable(received: MutableList<String>, expectedSize: Int) {
        withTimeout(5_000) {
            var lastSize = -1
            var stableCount = 0
            while (true) {
                val size = Collections.synchronizedList(received).size
                if (size == expectedSize && size == lastSize) {
                    stableCount++
                    if (stableCount >= 3) return@withTimeout
                } else {
                    stableCount = 0
                }
                lastSize = size
                kotlinx.coroutines.yield()
            }
        }
    }

    /** 等待条件成立，带超时，轮询。 */
    private suspend fun awaitCondition(timeoutMs: Long = 5_000, condition: () -> Boolean) {
        withTimeout(timeoutMs) {
            while (!condition()) {
                kotlinx.coroutines.yield()
            }
        }
    }

    // ---------------------------------------------------------------------
    // 1. 重复注册后旧 sink 收不到新消息，新 sink 能收到
    // ---------------------------------------------------------------------

    @Test
    fun `重复注册后旧 sink 收不到新消息新 sink 能收到`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)
        try {

                val oldReceived = Collections.synchronizedList(mutableListOf<String>())
                val newReceived = Collections.synchronizedList(mutableListOf<String>())

                val oldGate = CompletableDeferred<Unit>()

                // 旧 sink：先阻塞，模拟积压，再放行；重注册后旧协程应被取消。
                hub.register("A", BroadcastHub.FrameSink { text ->
                    oldGate.await()
                    oldReceived.add(text)
                }, this)

                // 给旧 slot 投递一条，使其卡在 sink 内（进入阻塞）。
                hub.broadcastExcept(null, "old-1")
                // 等待旧协程确实开始执行 sink（通过 received 未增长无法直接判断，改为等待一小段轮询其 job 状态不可靠，
                // 这里用 yield 让调度器推进；由于旧 sink 会 await gate，消息必然停在 sink 里）。
                repeat(100) { kotlinx.coroutines.yield() }

                // 重注册：同 clientId，旧的应被取消/关闭。
                hub.register("A", BroadcastHub.FrameSink { text ->
                    newReceived.add(text)
                }, this)

                // 释放旧 gate，即便旧协程未被取消也不会污染断言（旧 sink 记录到 oldReceived，但重注册后不应再有新消息进入旧 sink）。
                oldGate.complete(Unit)

                // 广播新消息，只应进入新 sink。
                hub.broadcastExcept(null, "new-1")
                hub.broadcastExcept(null, "new-2")

                drainUntilStable(newReceived, 2)
                assertEquals(listOf("new-1", "new-2"), newReceived.toList())
                // 旧 sink 不应收到任何新广播（new-1/new-2）。
                assertTrue(!oldReceived.contains("new-1")) { "旧 sink 不应收到 new-1，实际: $oldReceived" }
                assertTrue(!oldReceived.contains("new-2")) { "旧 sink 不应收到 new-2，实际: $oldReceived" }
        } finally {
            hub.unregister("A")
        }
    }

    // ---------------------------------------------------------------------
    // 2. 重注册后新 slot 的 seq 从 1 开始：发 3 条，新 sink 收到的 3 条无缺口（dropped 不增加）
    // ---------------------------------------------------------------------

    @Test
    fun `重注册后新 slot 的 seq 从 1 开始无缺口`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)
        try {

                val oldReceived = Collections.synchronizedList(mutableListOf<String>())
                val newReceived = Collections.synchronizedList(mutableListOf<String>())

                // 旧注册：先发一堆消息制造 seq 增长（用大容量快速消费，避免丢弃干扰）。
                hub.register("A", BroadcastHub.FrameSink { text ->
                    oldReceived.add(text)
                }, this)
                repeat(5) { hub.broadcastExcept(null, "old-$it") }
                drainUntilStable(oldReceived, 5)

                val droppedBefore = droppedTotal(metrics)

                // 重注册：新 slot 的 seq 应从 0 重新计数，发 3 条 => seq 1,2,3，无缺口。
                hub.register("A", BroadcastHub.FrameSink { text ->
                    newReceived.add(text)
                }, this)

                hub.broadcastExcept(null, "n-1")
                hub.broadcastExcept(null, "n-2")
                hub.broadcastExcept(null, "n-3")

                drainUntilStable(newReceived, 3)
                assertEquals(listOf("n-1", "n-2", "n-3"), newReceived.toList())

                // 新 slot 内部 seq 从 1 起，3 条连续消息无缺口 => dropped 不增加。
                val droppedAfter = droppedTotal(metrics)
                assertEquals(droppedBefore, droppedAfter, 0.0) {
                    "重注册后新 slot 无缺口，dropped 不应增加：before=$droppedBefore after=$droppedAfter"
                }
        } finally {
            hub.unregister("A")
        }
    }

    // ---------------------------------------------------------------------
    // 3. 重注册时旧 slot 队列里积压的未发送消息不泄漏到新 sink
    // ---------------------------------------------------------------------

    @Test
    fun `重注册时旧 slot 积压消息不泄漏到新 sink`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 4)
        try {

                val oldReceived = Collections.synchronizedList(mutableListOf<String>())
                val newReceived = Collections.synchronizedList(mutableListOf<String>())

                val gate = CompletableDeferred<Unit>()

                // 旧 sink 阻塞在 gate 上，让队列积压。
                hub.register("A", BroadcastHub.FrameSink { text ->
                    gate.await()
                    oldReceived.add(text)
                }, this)

                // 发多条：第一条进入 sink 卡住，其余留在旧 channel 队列里。
                repeat(4) { hub.broadcastExcept(null, "backlog-$it") }
                // 让旧协程把第一条取到 sink 内并阻塞。
                repeat(100) { kotlinx.coroutines.yield() }

                // 重注册：旧 slot 被关闭，旧队列积压应被丢弃（不会转移到新 sink）。
                hub.register("A", BroadcastHub.FrameSink { text ->
                    newReceived.add(text)
                }, this)

                // 释放 gate（旧协程可能已被取消，无所谓）。
                gate.complete(Unit)

                // 新广播只应到达新 sink。
                hub.broadcastExcept(null, "fresh-1")
                drainUntilStable(newReceived, 1)

                assertEquals(listOf("fresh-1"), newReceived.toList()) {
                    "新 sink 只应收到重注册后的新消息，旧积压不得泄漏"
                }
                assertTrue(newReceived.none { it.startsWith("backlog-") }) {
                    "旧 slot 积压消息泄漏到新 sink: $newReceived"
                }
        } finally {
            hub.unregister("A")
        }
    }

    // ---------------------------------------------------------------------
    // 4. unregister 不存在的 clientId 不抛异常（幂等）
    // ---------------------------------------------------------------------

    @Test
    fun `unregister 不存在的 clientId 不抛异常`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 4)
        try {

                // 未注册直接注销，应静默无操作。
                hub.unregister("never-registered")
                hub.unregister("never-registered")
                assertEquals(0, hub.sessionCount())

                // 注册后注销两次，第二次应幂等无异常。
                hub.register("A", BroadcastHub.FrameSink { }, this)
                assertEquals(1, hub.sessionCount())
                hub.unregister("A")
                assertEquals(0, hub.sessionCount())
                hub.unregister("A")
                assertEquals(0, hub.sessionCount())
        } finally {
            hub.unregister("A")
        }
    }

    // ---------------------------------------------------------------------
    // 5. unregister 后 broadcast 不再投递给它；sessionCount 减 1
    // ---------------------------------------------------------------------

    @Test
    fun `unregister 后不再投递且 sessionCount 减一`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)
        try {

                val received = Collections.synchronizedList(mutableListOf<String>())

                hub.register("A", BroadcastHub.FrameSink { text ->
                    received.add(text)
                }, this)

                hub.broadcastExcept(null, "before")
                drainUntilStable(received, 1)
                assertEquals(listOf("before"), received.toList())

                hub.unregister("A")
                assertEquals(0, hub.sessionCount())

                // 注销后再广播，不应再投递。
                hub.broadcastExcept(null, "after")
                // 给调度器机会推进（若有幽灵投递会被捕获）。
                repeat(200) { kotlinx.coroutines.yield() }

                assertEquals(listOf("before"), received.toList()) {
                    "注销后不应再收到消息，实际: $received"
                }
        } finally {
            hub.unregister("A")
        }
    }

    // ---------------------------------------------------------------------
    // 6. sink 抛异常时自动 unregister：后续广播不再投递，sessionCount 减 1
    // ---------------------------------------------------------------------

    @Test
    fun `sink 抛异常时自动 unregister`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)
        try {

                val received = Collections.synchronizedList(mutableListOf<String>())

                hub.register("A", BroadcastHub.FrameSink { text ->
                    received.add(text)
                    throw RuntimeException("boom")
                }, this)

                hub.broadcastExcept(null, "first")
                // 等待自动 unregister 生效。
                awaitCondition { hub.sessionCount() == 0 }

                assertEquals(0, hub.sessionCount()) { "sink 抛异常后应自动注销" }

                // 后续广播不再投递。
                hub.broadcastExcept(null, "second")
                repeat(200) { kotlinx.coroutines.yield() }
                assertEquals(listOf("first"), received.toList()) {
                    "异常注销后不应再收到消息，实际: $received"
                }
        } finally {
            hub.unregister("A")
        }
    }

    // ---------------------------------------------------------------------
    // 7. 连续注册 10 个不同 clientId 再逐个注销，sessionCount 归零，无泄漏（scope 结束）
    // ---------------------------------------------------------------------

    @Test
    fun `批量注册注销后 sessionCount 归零`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)

        val ids = (1..10).map { "client-$it" }

        // 注册 10 个，每个 sink 收到消息即记录。
        val perClient = Collections.synchronizedMap(HashMap<String, MutableList<String>>())
        ids.forEach { id ->
            perClient[id] = Collections.synchronizedList(mutableListOf<String>())
            hub.register(id, BroadcastHub.FrameSink { text ->
                perClient.getValue(id).add(text)
            }, this)
        }

        assertEquals(10, hub.sessionCount())

        // 广播一条，所有 10 个客户端都应收到。
        hub.broadcastExcept(null, "hello")
        awaitCondition { perClient.values.all { it.size == 1 } }
        perClient.forEach { (id, list) ->
            assertEquals(listOf("hello"), list.toList()) { "客户端 $id 应收到 hello" }
        }

        // 逐个注销，sessionCount 递减到 0。
        ids.forEach { id ->
            hub.unregister(id)
        }
        assertEquals(0, hub.sessionCount())

        // 注销后再广播，不应有任何投递。
        hub.broadcastExcept(null, "after-all")
        repeat(200) { kotlinx.coroutines.yield() }
        perClient.forEach { (id, list) ->
            assertEquals(listOf("hello"), list.toList()) { "客户端 $id 注销后不应再收到消息" }
        }
    }
}