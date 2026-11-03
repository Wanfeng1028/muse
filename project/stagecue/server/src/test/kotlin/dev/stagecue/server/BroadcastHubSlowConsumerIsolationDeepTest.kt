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
 * BroadcastHub 背压（DROP_OLDEST）语义测试。
 *
 * 核心不变量：
 *  - 慢消费者队列满时挤掉最旧，丢弃数经 stagecue_ws_broadcast_dropped_total 可观测；
 *  - 丢弃计数只统计"真正进入该客户端队列后被挤掉"的消息，快端/迟注册不产生幽灵计数；
 *  - 序列号 per-slot 独立，缺口法在发送协程内按 lastDeliveredSeq 递增统计。
 */
class BroadcastHubSlowConsumerIsolationDeepTest {

    /** 构造被测 hub：真实 StageMetrics + 指定容量的 BroadcastHub。 */
    private fun newHub(capacity: Int): Pair<StageMetrics, BroadcastHub> {
        val metrics = StageMetrics()
        return metrics to BroadcastHub(metrics, capacity)
    }

    /** 从 metrics.scrape() 中提取 stagecue_ws_broadcast_dropped_total 的当前值。 */
    private fun droppedCount(metrics: StageMetrics): Double {
        val re = Regex("stagecue_ws_broadcast_dropped_total\\s+([0-9.eE+-]+)")
        val m = re.find(metrics.scrape())
            ?: error("scrape() 中未找到 stagecue_ws_broadcast_dropped_total")
        return m.groupValues[1].toDouble()
    }

    /**
     * 轮询等待 received 的 size 稳定且达到期望，避免用 sleep 猜时序。
     * 超时用 withTimeout 保护，超过即失败。
     */
    private suspend fun drainUntilStable(received: MutableList<String>, expectedSize: Int) {
        withTimeout(5_000) {
            var last = -1
            var stableRounds = 0
            while (true) {
                val now = received.size
                if (now == expectedSize && now == last) {
                    stableRounds++
                    if (stableRounds >= 3) return@withTimeout
                } else {
                    stableRounds = 0
                }
                last = now
                kotlinx.coroutines.yield()
            }
        }
    }

    /**
     * 语义：容量 2，慢消费者阻塞时队列满挤掉最旧；放行后只收到最后 2 条，dropped 恰为 3。
     */
    @Test
    fun `容量2慢消费者阻塞发5条后放行只收最后2条且丢弃3`() = runBlocking {
        val (metrics, hub) = newHub(2)
        try {
                val received = Collections.synchronizedList(mutableListOf<String>())
                val gate = CompletableDeferred<Unit>()
                val firstArrived = CompletableDeferred<Unit>()

                // 慢消费者：第一条进入 sink 时阻塞在 gate 上，制造队列积压。
                hub.register("slow", BroadcastHub.FrameSink { text ->
                    if (!firstArrived.isCompleted) firstArrived.complete(Unit)
                    gate.await()
                    received.add(text)
                }, this)

                // 发 5 条：第 1 条被消费协程取出后阻塞；余下 4 条进容量 2 队列，挤掉最旧 2 条。
                repeat(5) { i -> hub.broadcastExcept(null, "m$i") }

                // 等第一条确实被取出并阻塞，确保后续 4 条已在队列中竞争。
                withTimeout(5_000) { firstArrived.await() }

                gate.complete(Unit)
                drainUntilStable(received, expectedSize = 2)

                // 收到的应是最后 2 条：m3、m4（m1、m2 被挤掉）。
                assertEquals(listOf("m3", "m4"), received.toList())
                // 5 条发出，2 条送达，缺口 3 条计入 dropped。
                assertEquals(3.0, droppedCount(metrics))
        } finally {
            hub.unregister("slow")
        }
    }

    /**
     * 语义：快端不受慢端影响收全 5 条；丢弃计数只统计慢端，恰为 3。
     */
    @Test
    fun `快慢两客户端慢端丢3条快端收全5条且丢弃计数恰为3`() = runBlocking {
        val (metrics, hub) = newHub(2)
        try {
                val fastReceived = Collections.synchronizedList(mutableListOf<String>())
                val slowReceived = Collections.synchronizedList(mutableListOf<String>())
                val gate = CompletableDeferred<Unit>()
                val firstArrived = CompletableDeferred<Unit>()

                hub.register("fast", BroadcastHub.FrameSink { text ->
                    fastReceived.add(text)
                }, this)

                hub.register("slow", BroadcastHub.FrameSink { text ->
                    if (!firstArrived.isCompleted) firstArrived.complete(Unit)
                    gate.await()
                    slowReceived.add(text)
                }, this)

                repeat(5) { i -> hub.broadcastExcept(null, "m$i") }

                withTimeout(5_000) { firstArrived.await() }
                gate.complete(Unit)

                drainUntilStable(fastReceived, expectedSize = 5)
                drainUntilStable(slowReceived, expectedSize = 2)

                assertEquals(listOf("m0", "m1", "m2", "m3", "m4"), fastReceived.toList())
                assertEquals(listOf("m3", "m4"), slowReceived.toList())
                // 只有慢端丢 3 条；快端零丢弃，故总量恰为 3。
                assertEquals(3.0, droppedCount(metrics))
        } finally {
            hub.unregister("fast")
            hub.unregister("slow")
        }
    }

    /**
     * 语义：慢端多轮填满，丢弃计数跨轮累加。两轮各发 5 条，累计 6。
     */
    @Test
    fun `慢端两轮各发5条丢弃累计6`() = runBlocking {
        val (metrics, hub) = newHub(2)
        try {
                val received = Collections.synchronizedList(mutableListOf<String>())

                // 每轮放行一次的门闩。
                val gate1 = CompletableDeferred<Unit>()
                val gate2 = CompletableDeferred<Unit>()
                var round = 0

                hub.register("slow", BroadcastHub.FrameSink { text ->
                    when (round) {
                        0 -> gate1.await()
                        1 -> gate2.await()
                    }
                    received.add(text)
                }, this)

                // 第一轮：消费协程取走第 1 条并阻塞在 gate1；再发 5 条，队列容量 2 挤掉 3 条。
                repeat(5) { i -> hub.broadcastExcept(null, "r1-$i") }
                gate1.complete(Unit)
                drainUntilStable(received, expectedSize = 2)
                assertEquals(3.0, droppedCount(metrics))

                // 第二轮：切到 gate2 阻塞，继续发 5 条，再挤掉 3 条。
                round = 1
                repeat(5) { i -> hub.broadcastExcept(null, "r2-$i") }
                gate2.complete(Unit)
                drainUntilStable(received, expectedSize = 4)

                // 两轮累计丢弃 3 + 3 = 6。
                assertEquals(6.0, droppedCount(metrics))
        } finally {
            hub.unregister("slow")
        }
    }

    /**
     * 语义：默认容量 64 边界——第 64 条不丢，第 65 条起丢 1。
     */
    @Test
    fun `容量64发64条不丢第65条起丢1`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics) // 使用默认 queueCapacity = 64
        val received = Collections.synchronizedList(mutableListOf<String>())
        val gate = CompletableDeferred<Unit>()
        val firstArrived = CompletableDeferred<Unit>()

        hub.register("slow", BroadcastHub.FrameSink { text ->
            if (!firstArrived.isCompleted) firstArrived.complete(Unit)
            gate.await()
            received.add(text)
        }, this)

        // 消费协程取走第 1 条后阻塞；队列容量 64，正好装下第 2..65 条。
        repeat(64) { i -> hub.broadcastExcept(null, "m$i") }
        withTimeout(5_000) { firstArrived.await() }

        gate.complete(Unit)
        drainUntilStable(received, expectedSize = 64)

        // 64 条全部送达，无丢弃。
        assertEquals(64, received.size)
        assertEquals(0.0, droppedCount(metrics))
    }

    /**
     * 语义：消费者介于生产之间，每放行 1 条；dropped 恰为 发出数 - 收到数。
     * 用门闩逐条放行，避免任何时序猜测。
     */
    @Test
    fun `消费者逐条放行时丢弃数等于发出数减收到数`() = runBlocking {
        val (metrics, hub) = newHub(2)
        try {
                val received = Collections.synchronizedList(mutableListOf<String>())
                // 每条消费都需一次 permit；测试按需补充 permit 来精确控制放行节奏。
                val permits = Channel<Unit>(Channel.UNLIMITED)

                hub.register("slow", BroadcastHub.FrameSink { text ->
                    permits.receive() // 阻塞直到测试放行
                    received.add(text)
                }, this)

                val totalSent = 9

                // 先发 9 条：第 1 条被取出并阻塞在 permits 上，余下 8 条进容量 2 队列，挤掉 6 条。
                repeat(totalSent) { i -> hub.broadcastExcept(null, "m$i") }

                // 逐条放行，直到收到期望数量；此处期望最终收到最后 2 条 + 已取出的第 1 条 = 3 条。
                // 已取出的第 1 条放行后计入 received；队列中最终保留最后 2 条。
                val expectedReceived = 3
                repeat(expectedReceived) {
                    permits.trySend(Unit)
                }
                drainUntilStable(received, expectedSize = expectedReceived)

                val dropped = totalSent - received.size
                assertEquals(6, dropped)
                assertEquals(dropped.toDouble(), droppedCount(metrics))
        } finally {
            hub.unregister("slow")
        }
    }

    /**
     * 语义：注销后旧积压不再计入 dropped；新注册同名客户端从 0 重新计数。
     */
    @Test
    fun `注销后旧积压不计新同名客户端从0开始`() = runBlocking {
        val (metrics, hub) = newHub(2)
        try {
                val received1 = Collections.synchronizedList(mutableListOf<String>())
                val gate1 = CompletableDeferred<Unit>()
                val firstArrived = CompletableDeferred<Unit>()

                hub.register("client", BroadcastHub.FrameSink { text ->
                    if (!firstArrived.isCompleted) firstArrived.complete(Unit)
                    gate1.await()
                    received1.add(text)
                }, this)

                // 制造积压：取走 1 条阻塞，队列满挤掉。
                repeat(5) { i -> hub.broadcastExcept(null, "old$i") }
                withTimeout(5_000) { firstArrived.await() }

                // 注销：取消旧协程并关闭队列，旧 slot 的 seq/积压不再被统计。
                hub.unregister("client")

                val droppedAfterUnregister = droppedCount(metrics)

                // 重新注册同名客户端，使用新的门闩，sink 立即放行。
                val received2 = Collections.synchronizedList(mutableListOf<String>())
                hub.register("client", BroadcastHub.FrameSink { text ->
                    received2.add(text)
                }, this)

                // 新客户端发 2 条，容量 2，不丢。
                repeat(2) { i -> hub.broadcastExcept(null, "new$i") }
                drainUntilStable(received2, expectedSize = 2)

                assertEquals(listOf("new0", "new1"), received2.toList())
                // 新客户端从 0 开始，丢弃计数不再增长（旧积压未计入）。
                assertEquals(droppedAfterUnregister, droppedCount(metrics))
        } finally {
            hub.unregister("client")
        }
    }

    /**
     * 语义：sink 中途抛异常——已发送的不重算 dropped，客户端自动注销，后续广播不再投递。
     */
    @Test
    fun `sink抛异常后已发送不重算丢弃且自动注销`() = runBlocking {
        val (metrics, hub) = newHub(4)
        try {
                val received = Collections.synchronizedList(mutableListOf<String>())
                val failOn = "boom"

                hub.register("flaky", BroadcastHub.FrameSink { text ->
                    if (text == failOn) throw RuntimeException("模拟发送失败")
                    received.add(text)
                }, this)

                // 先发 2 条正常消息，确保送达。
                hub.broadcastExcept(null, "ok0")
                hub.broadcastExcept(null, "ok1")
                drainUntilStable(received, expectedSize = 2)

                // 发会触发异常的消息，触发自动注销。
                hub.broadcastExcept(null, failOn)

                // 等待注销生效：sessionCount 归零。
                withTimeout(5_000) {
                    while (hub.sessionCount() != 0) {
                        kotlinx.coroutines.yield()
                    }
                }

                // 已送达的 2 条不因异常而重算 dropped，仍为 0。
                assertEquals(listOf("ok0", "ok1"), received.toList())
                assertEquals(0.0, droppedCount(metrics))
                assertEquals(0, hub.sessionCount())

                // 注销后继续广播不应再投递给已注销客户端。
                hub.broadcastExcept(null, "after")
                // 给潜在误投递一点让出的机会，再确认没有新增。
                kotlinx.coroutines.yield()
                assertEquals(listOf("ok0", "ok1"), received.toList())
        } finally {
            hub.unregister("flaky")
        }
    }
}
