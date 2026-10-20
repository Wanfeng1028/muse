package dev.stagecue.server

import dev.stagecue.server.ws.BroadcastHub

import dev.stagecue.server.metrics.StageMetrics
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.util.Collections

class BroadcastHubPerSlotSeqDeepTest {

    // 从 metrics.scrape() 中提取广播丢弃计数
    private fun droppedCount(metrics: StageMetrics): Double {
        val text = metrics.scrape()
        val m = Regex("stagecue_ws_broadcast_dropped_total\\s+([0-9.eE+-]+)").find(text)
            ?: return 0.0
        return m.groupValues[1].toDouble()
    }

    // 轮询等待 received 集合大小稳定在 expectedSize
    private suspend fun drainUntilStable(received: MutableList<String>, expectedSize: Int) {
        withTimeout(10_000) {
            var lastSize = -1
            var stable = 0
            while (true) {
                val size = synchronized(received) { received.size }
                if (size == expectedSize && size == lastSize) {
                    stable++
                    if (stable >= 3) return@withTimeout
                } else {
                    stable = 0
                }
                lastSize = size
                delay(10)
            }
        }
    }


    // 轮询等待 received 集合大小稳定（未知目标大小，用于确认不再变化）
    private fun drainUntilQuiescent(received: MutableList<String>) {
        var lastSize = -1
        var stableCount = 0
        val deadline = System.currentTimeMillis() + 2000
        while (System.currentTimeMillis() < deadline) {
            val size = synchronized(received) { received.size }
            if (size == lastSize) {
                stableCount++
                if (stableCount >= 5) return
            } else {
                stableCount = 0
                lastSize = size
            }
            Thread.sleep(5)
        }
    }

    /**
     * 语义：两个客户端各自独立收齐全部广播，per-slot 序列号连续，缺口为 0，丢弃计数为 0。
     */
    @Test
    fun `两客户端各收三条广播缺口为零且丢弃计数为零`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)
        try {
                val receivedA = Collections.synchronizedList(mutableListOf<String>())
                val receivedB = Collections.synchronizedList(mutableListOf<String>())

                hub.register("A", BroadcastHub.FrameSink { text -> receivedA.add(text) }, this)
                hub.register("B", BroadcastHub.FrameSink { text -> receivedB.add(text) }, this)

                hub.broadcastExcept(null, "m1")
                hub.broadcastExcept(null, "m2")
                hub.broadcastExcept(null, "m3")

                drainUntilStable(receivedA, 3)
                drainUntilStable(receivedB, 3)

                assertEquals(listOf("m1", "m2", "m3"), synchronized(receivedA) { receivedA.toList() })
                assertEquals(listOf("m1", "m2", "m3"), synchronized(receivedB) { receivedB.toList() })
                assertEquals(0.0, droppedCount(metrics))
        } finally {
            hub.unregister("A")
            hub.unregister("B")
        }
    }

    /**
     * 语义：broadcastExcept 只跳过被排除客户端，其 seq 不递增，因此后续全量广播时该客户端
     * 的 per-slot 序列号仍然连续，缺口为 0。
     */
    @Test
    fun `broadcastExcept 排除后序列号不跳号`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)
        try {
                val receivedA = Collections.synchronizedList(mutableListOf<String>())
                val receivedB = Collections.synchronizedList(mutableListOf<String>())

                hub.register("A", BroadcastHub.FrameSink { text -> receivedA.add(text) }, this)
                hub.register("B", BroadcastHub.FrameSink { text -> receivedB.add(text) }, this)

                // 排除 A 的广播：A 收不到，B 收到
                hub.broadcastExcept("A", "onlyB")

                drainUntilStable(receivedB, 1)

                assertEquals(0, synchronized(receivedA) { receivedA.size })
                assertEquals(listOf("onlyB"), synchronized(receivedB) { receivedB.toList() })

                // 全量广播，A 与 B 各自 seq 连续
                hub.broadcastExcept(null, "all1")
                hub.broadcastExcept(null, "all2")

                drainUntilStable(receivedA, 2)
                drainUntilStable(receivedB, 3)

                assertEquals(listOf("all1", "all2"), synchronized(receivedA) { receivedA.toList() })
                assertEquals(listOf("onlyB", "all1", "all2"), synchronized(receivedB) { receivedB.toList() })
                assertEquals(0.0, droppedCount(metrics))
        } finally {
            hub.unregister("A")
            hub.unregister("B")
        }
    }

    /**
     * 语义：迟注册的 B 只统计自己的丢弃，不把 A 的历史广播算成自己的缺口；
     * B 队列 capacity=2 且 sink 阻塞时，3 条广播挤掉最旧 1 条，B 收到最后 2 条，dropped=1。
     * A 的 dropped 不受影响。
     */
    @Test
    fun `lateRegisteredClientHasNoPhantomDrops_迟注册客户端不产生幽灵丢弃`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 2)
        try {
            val receivedA = Collections.synchronizedList(mutableListOf<String>())
            val receivedB = Collections.synchronizedList(mutableListOf<String>())

            // A 先注册并收齐 3 条，dropped 为 0（基线）
            hub.register("A", BroadcastHub.FrameSink { text -> receivedA.add(text) }, this)
            hub.broadcastExcept(null, "a1")
            hub.broadcastExcept(null, "a2")
            hub.broadcastExcept(null, "a3")
            drainUntilStable(receivedA, 3)
            assertEquals(0.0, droppedCount(metrics), "基线 dropped 应为 0")

            // B 迟注册，sink 阻塞在门闩上；enteredB 确认 sender 已取走 b1 并阻塞
            val gateB = CompletableDeferred<Unit>()
            val enteredB = CompletableDeferred<Unit>()
            hub.register("B", BroadcastHub.FrameSink { text ->
                enteredB.complete(Unit)
                gateB.await()
                receivedB.add(text)
            }, this)

            // 先广播 b1 并等待 B 的 sender 取走它（阻塞在门闩上），消除时序竞态
            hub.broadcastExcept(null, "b1")
            withTimeout(5_000) { enteredB.await() }

            // 再广播 b2/b3/b4：b2/b3 进队列（容量 2 满），b4 到达时挤掉最旧的 b2 → B 恰丢 1 条
            hub.broadcastExcept(null, "b2")
            hub.broadcastExcept(null, "b3")
            hub.broadcastExcept(null, "b4")

            // 放开门闩，B 收到 [b1, b3, b4]
            gateB.complete(Unit)
            drainUntilStable(receivedB, 3)

            assertEquals(listOf("b1", "b3", "b4"), synchronized(receivedB) { receivedB.toList() },
                "B 应收到 b1/b3/b4（b2 被挤掉）")
            assertEquals(1.0, droppedCount(metrics),
                "dropped 应恰为 1（仅 B 的 b2），迟注册不产生幽灵丢弃")
        } finally {
            hub.unregister("A")
            hub.unregister("B")
        }
    }

    /**
     * 语义：被排除的广播根本不进入该客户端队列，因此不产生丢弃计数。
     */
    @Test
    fun `excludedBroadcastHasNoPhantomDrops_被排除的广播不产生幽灵丢弃`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 2)
        try {
                val receivedA = Collections.synchronizedList(mutableListOf<String>())

                hub.register("A", BroadcastHub.FrameSink { text -> receivedA.add(text) }, this)

                // 广播 3 条但排除 A：A 队列毫无压力
                hub.broadcastExcept("A", "x1")
                hub.broadcastExcept("A", "x2")
                hub.broadcastExcept("A", "x3")

                drainUntilQuiescent(receivedA)

                assertEquals(0, synchronized(receivedA) { receivedA.size })
                assertEquals(0.0, droppedCount(metrics))

                // 再广播 3 条包含 A：A 容量 2，挤掉最旧 1 条
                hub.broadcastExcept(null, "y1")
                hub.broadcastExcept(null, "y2")
                hub.broadcastExcept(null, "y3")

                drainUntilStable(receivedA, 2)

                assertEquals(listOf("y2", "y3"), synchronized(receivedA) { receivedA.toList() })
                assertEquals(1.0, droppedCount(metrics))
        } finally {
            hub.unregister("A")
        }
    }

    /**
     * 语义：容量为 1 的极端情况下，连续 5 条广播且消费者阻塞时，只有最后 1 条存活，
     * 缺口计数为 4。
     */
    @Test
    fun `容量一的极端下只保留最后一条并计四次丢弃`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 1)
        try {
                val received = Collections.synchronizedList(mutableListOf<String>())
                val gate = CompletableDeferred<Unit>()

                hub.register("A", BroadcastHub.FrameSink { text ->
                    gate.await()
                    received.add(text)
                }, this)

                hub.broadcastExcept(null, "e1")
                hub.broadcastExcept(null, "e2")
                hub.broadcastExcept(null, "e3")
                hub.broadcastExcept(null, "e4")
                hub.broadcastExcept(null, "e5")

                // 放开阻塞，消费最后一条
                gate.complete(Unit)

                drainUntilStable(received, 1)

                assertEquals(listOf("e5"), synchronized(received) { received.toList() })
                assertEquals(4.0, droppedCount(metrics))
        } finally {
            hub.unregister("A")
        }
    }

    /**
     * 语义：注销后重注册会创建新 Slot，per-slot 序列号从 1 重新开始，不与旧序列混淆，
     * 也不会产生虚假缺口。
     */
    @Test
    fun `注销后重注册序列号从一重新开始`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)
        try {
                val receivedFirst = Collections.synchronizedList(mutableListOf<String>())

                hub.register("A", BroadcastHub.FrameSink { text -> receivedFirst.add(text) }, this)

                hub.broadcastExcept(null, "f1")
                hub.broadcastExcept(null, "f2")
                drainUntilStable(receivedFirst, 2)

                hub.unregister("A")
                drainUntilQuiescent(receivedFirst)

                // 重注册：新 Slot，seq 从 1 开始
                val receivedSecond = Collections.synchronizedList(mutableListOf<String>())
                hub.register("A", BroadcastHub.FrameSink { text -> receivedSecond.add(text) }, this)

                hub.broadcastExcept(null, "g1")
                hub.broadcastExcept(null, "g2")

                drainUntilStable(receivedSecond, 2)

                assertEquals(listOf("g1", "g2"), synchronized(receivedSecond) { receivedSecond.toList() })
                // 新 Slot 第一条 seq=1，无缺口
                assertEquals(0.0, droppedCount(metrics))
        } finally {
            hub.unregister("A")
        }
    }

    /**
     * 语义：空 hub 广播不抛异常；sessionCount 准确反映当前注册数。
     */
    @Test
    fun `空hub广播不抛异常且sessionCount准确`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 4)
        try {

                assertEquals(0, hub.sessionCount())

                // 空 hub 广播不应抛异常
                hub.broadcastExcept(null, "noop")
                hub.broadcastExcept("X", "noop2")

                assertEquals(0, hub.sessionCount())
                assertEquals(0.0, droppedCount(metrics))

                val received = Collections.synchronizedList(mutableListOf<String>())
                hub.register("A", BroadcastHub.FrameSink { text -> received.add(text) }, this)
                assertEquals(1, hub.sessionCount())

                hub.register("B", BroadcastHub.FrameSink { text -> received.add(text) }, this)
                assertEquals(2, hub.sessionCount())

                hub.unregister("A")
                assertEquals(1, hub.sessionCount())

                hub.unregister("B")
                assertEquals(0, hub.sessionCount())

                // 注销不存在的客户端是幂等的
                hub.unregister("A")
                assertEquals(0, hub.sessionCount())
        } finally {
            hub.unregister("A")
            hub.unregister("B")
        }
    }

    /**
     * 语义：同一 clientId 重复注册会先注销旧 Slot，旧 sink 不再收到消息。
     */
    @Test
    fun `同一clientId重复注册旧sink不再收到消息`() = runBlocking {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, queueCapacity = 8)
        try {
                val receivedOld = Collections.synchronizedList(mutableListOf<String>())
                val receivedNew = Collections.synchronizedList(mutableListOf<String>())

                hub.register("A", BroadcastHub.FrameSink { text -> receivedOld.add(text) }, this)
                hub.broadcastExcept(null, "old1")
                drainUntilStable(receivedOld, 1)

                // 重复注册：旧 sink 被替换
                hub.register("A", BroadcastHub.FrameSink { text -> receivedNew.add(text) }, this)

                hub.broadcastExcept(null, "new1")
                hub.broadcastExcept(null, "new2")

                drainUntilStable(receivedNew, 2)

                assertEquals(1, hub.sessionCount())
                assertEquals(listOf("new1", "new2"), synchronized(receivedNew) { receivedNew.toList() })
                // 旧 sink 在替换后不再新增
                assertEquals(1, synchronized(receivedOld) { receivedOld.size })
                assertEquals(listOf("old1"), synchronized(receivedOld) { receivedOld.toList() })
                assertEquals(0.0, droppedCount(metrics))
        } finally {
            hub.unregister("A")
        }
    }
}
