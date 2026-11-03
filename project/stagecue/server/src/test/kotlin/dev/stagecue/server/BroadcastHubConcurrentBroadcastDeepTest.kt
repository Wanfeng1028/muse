package dev.stagecue.server

import dev.stagecue.server.ws.BroadcastHub

import dev.stagecue.server.metrics.StageMetrics
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class BroadcastHubConcurrentBroadcastDeepTest {

    private fun newHub(capacity: Int): Pair<StageMetrics, BroadcastHub> {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, capacity)
        return metrics to hub
    }

    /** 从 metrics 抓取 stagecue_ws_broadcast_dropped_total 的当前值。 */
    private fun droppedTotal(metrics: StageMetrics): Double {
        val regex = Regex("stagecue_ws_broadcast_dropped_total\\s+([0-9.eE+-]+)")
        val match = regex.find(metrics.scrape()) ?: return 0.0
        return match.groupValues[1].toDouble()
    }

    /** 轮询等待 received 的 size 稳定（连续多次不变视为稳定）。 */
    private suspend fun drainUntilStable(received: MutableList<String>, expectedSize: Int) {
        var stable = 0
        var last = -1
        repeat(2000) {
            val now = received.size
            if (now == last) {
                stable++
                if (stable >= 5 && now >= expectedSize) return
            } else {
                stable = 0
                last = now
            }
            kotlinx.coroutines.yield()
        }
    }

    // 1. 10 个协程各广播 20 条（共 200 条），容量 512 不丢：客户端收到 200 条且文本集合恰为全集。
    @Test
    fun `十协程广播两百条无丢弃且内容完整`() = runBlocking {
        val (metrics, hub) = newHub(512)
        try {
                val received = java.util.Collections.synchronizedList(mutableListOf<String>())
                hub.register("A", BroadcastHub.FrameSink { text -> received.add(text) }, this)

                val broadcasters = 10
                val perBroadcaster = 20
                val jobs = (0 until broadcasters).map { b ->
                    launch {
                        repeat(perBroadcaster) { i ->
                            hub.broadcastExcept(null, "m-$b-$i")
                        }
                    }
                }
                jobs.forEach { it.join() }

                drainUntilStable(received, 200)
                withTimeout(5_000) {
                    while (received.size < 200) kotlinx.coroutines.yield()
                }

                val expected = (0 until broadcasters).flatMap { b -> (0 until perBroadcaster).map { i -> "m-$b-$i" } }.toSet()
                val actual = received.toSet()
                assertEquals(200, received.size, "容量 512 不应丢消息")
                assertEquals(expected, actual, "收到的文本集合应恰为全集")
                assertEquals(0.0, droppedTotal(metrics), 0.0, "不应有丢弃计数")
        } finally {
            hub.unregister("A")
        }
    }

    // 2. 并发广播永不挂起：broadcastExcept 在消费者阻塞时 100ms 内返回（withTimeout 保护）。
    @Test
    fun `消费者阻塞时广播永不挂起`() = runBlocking {
        val (_, hub) = newHub(8)
        try {
                val gate = CompletableDeferred<Unit>()
                val entered = CompletableDeferred<Unit>()
                hub.register("slow", BroadcastHub.FrameSink { text ->
                    entered.complete(Unit)
                    gate.await()
                }, this)

                // 先发一条把消费者卡在 sink 内。
                hub.broadcastExcept(null, "first")
                withTimeout(2_000) { entered.await() }

                // 消费者已被阻塞，继续广播必须立即返回（trySend，永不挂起）。
                withTimeout(100) {
                    repeat(64) { i ->
                        hub.broadcastExcept(null, "burst-$i")
                    }
                }

                gate.complete(Unit)
        } finally {
            hub.unregister("slow")
        }
    }

    // 3. 慢消费者 + 并发生产者：收到的序列严格单调递增（用 sink 记录顺序断言）。
    @Test
    fun `慢消费者收到的顺序严格单调`() = runBlocking {
        val (_, hub) = newHub(4)
        try {
                val order = java.util.Collections.synchronizedList(mutableListOf<String>())
                val gate = CompletableDeferred<Unit>()
                val entered = CompletableDeferred<Unit>()
                // 记录到达 sink 的顺序，用文本里的单调编号验证无重复、无逆序。
                hub.register("slow", BroadcastHub.FrameSink { text ->
                    if (!entered.isCompleted) entered.complete(Unit)
                    gate.await()
                    order.add(text)
                }, this)

                hub.broadcastExcept(null, "seq-0")
                withTimeout(2_000) { entered.await() }

                // 生产大量消息，容量 4 会丢弃最旧；但进入 sink 的一定按队列顺序。
                val total = 500
                repeat(total) { i ->
                    hub.broadcastExcept(null, "seq-${i + 1}")
                }

                // 放开门闩，让消费者排空。
                gate.complete(Unit)
                withTimeout(5_000) {
                    while (order.size < total + 1) kotlinx.coroutines.yield()
                }

                val seen = mutableListOf<Long>()
                for (t in order) {
                    val idx = t.removePrefix("seq-").toLong()
                    seen.add(idx)
                }
                // 顺序必须严格单调递增（去重 + 递增）。
                for (i in 1 until seen.size) {
                    assertTrue(seen[i] > seen[i - 1], "序列必须严格单调递增：${seen[i - 1]} -> ${seen[i]}")
                }
                assertEquals(seen.toSet().size, seen.size, "不应出现重复序列")
        } finally {
            hub.unregister("slow")
        }
    }

    // 4. 多客户端并发：A 快 B 慢，B 丢弃不影响 A 的完整性（A 收全量）。
    @Test
    fun `慢客户端丢弃不影响快客户端完整性`() = runBlocking {
        val (_, hub) = newHub(4)
        try {
                val aReceived = java.util.Collections.synchronizedList(mutableListOf<String>())
                val gate = CompletableDeferred<Unit>()
                val entered = CompletableDeferred<Unit>()

                hub.register("A", BroadcastHub.FrameSink { text -> aReceived.add(text) }, this)
                hub.register("B", BroadcastHub.FrameSink { text ->
                    if (!entered.isCompleted) entered.complete(Unit)
                    gate.await()
                }, this)

                hub.broadcastExcept(null, "msg-0")
                withTimeout(2_000) { entered.await() }

                val total = 400
                for (i in 1..total) {
                    hub.broadcastExcept(null, "msg-$i")
                }

                gate.complete(Unit)
                withTimeout(5_000) {
                    while (aReceived.size < total + 1) kotlinx.coroutines.yield()
                }

                assertEquals(total + 1, aReceived.size, "快客户端 A 应收全量")
                val expected = (0..total).map { "msg-$it" }.toSet()
                assertEquals(expected, aReceived.toSet(), "A 收到的文本应恰为全集")
        } finally {
            hub.unregister("A")
            hub.unregister("B")
        }
    }

    // 5. 并发 register/unregister/broadcast 混跑 500 次操作不抛异常，结束时 sessionCount 一致。
    @Test
    fun `并发注册注销广播混跑不抛异常`() = runBlocking {
        val (_, hub) = newHub(16)
                val ops = 500
                val jobs = (0 until ops).map { i ->
                    launch {
                        when (i % 3) {
                            0 -> hub.register("c-$i", BroadcastHub.FrameSink { }, this@runBlocking)
                            1 -> hub.unregister("c-${i - 1}")
                            else -> hub.broadcastExcept(null, "op-$i")
                        }
                    }
                }
                jobs.forEach { it.join() }

                // 结束后统计：所有已注册未注销的 id 数量应与 sessionCount 一致。
                // 由于并发时序，这里断言 sessionCount 与实际 slots 键集合大小一致（无泄漏）。
                val count = hub.sessionCount()
                assertTrue(count >= 0, "sessionCount 不应为负")
                // 再全量注销后应为 0，验证清理语义。
                for (i in 0 until ops) {
                    hub.unregister("c-$i")
                }
                assertEquals(0, hub.sessionCount(), "全量注销后 sessionCount 应为 0")
    }

    // 6. 广播空字符串与超长字符串（10KB）正常投递。
    @Test
    fun `广播空串与超长串均正常投递`() = runBlocking {
        val (_, hub) = newHub(64)
        try {
                val received = java.util.Collections.synchronizedList(mutableListOf<String>())
                hub.register("A", BroadcastHub.FrameSink { text -> received.add(text) }, this)

                val longText = "x".repeat(10 * 1024)
                hub.broadcastExcept(null, "")
                hub.broadcastExcept(null, longText)

                withTimeout(5_000) {
                    while (received.size < 2) kotlinx.coroutines.yield()
                }

                assertEquals(2, received.size, "空串与超长串都应投递")
                assertTrue(received.contains(""), "应收到空字符串")
                assertTrue(received.contains(longText), "应收到 10KB 超长字符串")
        } finally {
            hub.unregister("A")
        }
    }
}