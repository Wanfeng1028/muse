package dev.stagecue.server

import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.server.ws.BroadcastHub
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.util.Collections

class BroadcastHubBackpressureDeepTestR2Test {

    private class HubAndSink(
        val hub: BroadcastHub,
        val metrics: StageMetrics,
    )

    private fun newHub(capacity: Int): HubAndSink {
        val metrics = StageMetrics()
        val hub = BroadcastHub(metrics, capacity)
        return HubAndSink(hub, metrics)
    }

    private fun droppedCount(scrape: String): Double {
        val regex = Regex("stagecue_ws_broadcast_dropped_total\\s+([0-9.eE+-]+)")
        val m = regex.find(scrape) ?: return 0.0
        return m.groupValues[1].toDouble()
    }

    private suspend fun drainUntilStable(
        received: List<String>,
        expectedSize: Int,
        timeoutMs: Long = 5000,
    ) {
        withTimeout(timeoutMs) {
            var lastSize = -1
            while (true) {
                val size = synchronized(received) { received.size }
                if (size == expectedSize && size == lastSize) return@withTimeout
                lastSize = size
                delay(10)
            }
        }
    }

    @Test
    fun `late registration counts no phantom drops`() = runBlocking {
        val h = newHub(2)
        val scope = this

        val receivedA = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("A", { text -> receivedA.add(text) }, scope)

        for (i in 1..5) {
            h.hub.broadcastExcept(null, "a$i")
            yield()
        }
        drainUntilStable(receivedA, 5)

        // Phase B1: b1..b3 发给 A（此时 B 尚未注册，只有 A 在线）。A 是 fast consumer，yield 排空，A 不丢。
        for (i in 1..3) {
            h.hub.broadcastExcept(null, "b$i")
            yield()
        }

        // 注册 B（gate 卡住）。关键：从 register 到 Phase B2 结束，主线程没有任何挂起点，
        // B 的 consumer 协程还没机会运行，channel 处于无人接收状态——
        // b1/b2/b3 全部进 buffer，b1 被 DROP_OLDEST 挤掉（Kotlin channel 在有等待接收者时会直接 handoff 绕过 buffer，
        // 若 B 的 consumer 已在运行，b1 会被直接交到它手里而不会被挤掉，测试就失去意义）。
        val gateB = CompletableDeferred<Unit>()
        val receivedB = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("B", { text ->
            gateB.await()
            receivedB.add(text)
        }, scope)

        // Phase B2: b1..b3 只发给 B，不 yield。B 的 consumer 尚未运行，无 handoff，b1 被挤掉，B 收到 [b2, b3]。
        for (i in 1..3) {
            h.hub.broadcastExcept("A", "b$i")
        }
        gateB.complete(Unit)

        drainUntilStable(receivedB, 2)
        delay(50)

        try {
            assertEquals(listOf("b2", "b3"), synchronized(receivedB) { receivedB.toList() })
            assertEquals(1.0, droppedCount(h.metrics.scrape()))
            assertEquals(8, synchronized(receivedA) { receivedA.size })
        } finally {
            h.hub.unregister("A")
            h.hub.unregister("B")
        }
    }

    @Test
    fun `re-registration starts drop accounting fresh`() = runBlocking {
        val h = newHub(2)
        val scope = this

        val gate1 = CompletableDeferred<Unit>()
        val received1 = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("C", { text ->
            gate1.await()
            received1.add(text)
        }, scope)

        for (i in 1..3) h.hub.broadcastExcept(null, "m$i")
        gate1.complete(Unit)
        drainUntilStable(received1, 2)
        delay(50)

        val d1 = droppedCount(h.metrics.scrape())
        assertEquals(1.0, d1)

        h.hub.unregister("C")

        val gate2 = CompletableDeferred<Unit>()
        val received2 = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("C", { text ->
            gate2.await()
            received2.add(text)
        }, scope)

        for (i in 1..2) h.hub.broadcastExcept(null, "n$i")
        gate2.complete(Unit)
        drainUntilStable(received2, 2)
        delay(50)

        try {
            assertEquals(2, synchronized(received2) { received2.size })

            val d2 = droppedCount(h.metrics.scrape())
            assertEquals(0.0, d2 - d1)
            assertEquals(d1, d2)
        } finally {
            h.hub.unregister("C")
        }
    }

    @Test
    fun `excluded broadcasts are not counted as drops`() = runBlocking {
        val h = newHub(4)
        val scope = this

        val receivedA = Collections.synchronizedList(mutableListOf<String>())
        val receivedB = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("A", { text -> receivedA.add(text) }, scope)
        h.hub.register("B", { text -> receivedB.add(text) }, scope)

        for (i in 1..3) h.hub.broadcastExcept("A", "x$i")
        h.hub.broadcastExcept(null, "y1")

        drainUntilStable(receivedB, 4)
        drainUntilStable(receivedA, 1)
        delay(50)

        try {
            assertEquals(listOf("y1"), synchronized(receivedA) { receivedA.toList() })
            assertEquals(4, synchronized(receivedB) { receivedB.size })
            assertEquals(0.0, droppedCount(h.metrics.scrape()))
        } finally {
            h.hub.unregister("A")
            h.hub.unregister("B")
        }
    }

    @Test
    fun `drop oldest keeps newest on exact overflow by one`() = runBlocking {
        val h = newHub(2)
        val scope = this

        val gate = CompletableDeferred<Unit>()
        val received = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("D", { text ->
            gate.await()
            received.add(text)
        }, scope)

        h.hub.broadcastExcept(null, "m1")
        h.hub.broadcastExcept(null, "m2")
        h.hub.broadcastExcept(null, "m3")
        gate.complete(Unit)
        drainUntilStable(received, 2)
        delay(50)

        try {
            assertEquals(listOf("m2", "m3"), synchronized(received) { received.toList() })
            assertEquals(1.0, droppedCount(h.metrics.scrape()))
        } finally {
            h.hub.unregister("D")
        }
    }

    @Test
    fun `no drops when message count equals capacity`() = runBlocking {
        val h = newHub(3)
        val scope = this

        val gate = CompletableDeferred<Unit>()
        val received = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("E", { text ->
            gate.await()
            received.add(text)
        }, scope)

        h.hub.broadcastExcept(null, "m1")
        h.hub.broadcastExcept(null, "m2")
        h.hub.broadcastExcept(null, "m3")
        gate.complete(Unit)
        drainUntilStable(received, 3)
        delay(50)

        try {
            assertEquals(listOf("m1", "m2", "m3"), synchronized(received) { received.toList() })
            assertEquals(0.0, droppedCount(h.metrics.scrape()))
        } finally {
            h.hub.unregister("E")
        }
    }

    @Test
    fun `dropped counter is cumulative across episodes`() = runBlocking {
        val h = newHub(2)
        val scope = this

        val gate1 = CompletableDeferred<Unit>()
        val received1 = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("F", { text ->
            gate1.await()
            received1.add(text)
        }, scope)

        for (i in 1..4) h.hub.broadcastExcept(null, "m$i")
        gate1.complete(Unit)
        drainUntilStable(received1, 2)
        delay(50)

        assertEquals(listOf("m3", "m4"), synchronized(received1) { received1.toList() })
        val d1 = droppedCount(h.metrics.scrape())
        assertEquals(2.0, d1)

        h.hub.unregister("F")

        val gate2 = CompletableDeferred<Unit>()
        val received2 = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("F", { text ->
            gate2.await()
            received2.add(text)
        }, scope)

        for (i in 1..4) h.hub.broadcastExcept(null, "n$i")
        gate2.complete(Unit)
        drainUntilStable(received2, 2)
        delay(50)

        try {
            assertEquals(listOf("n3", "n4"), synchronized(received2) { received2.toList() })
            val d2 = droppedCount(h.metrics.scrape())
            assertEquals(2.0, d2 - d1)
            assertEquals(4.0, d2)
        } finally {
            h.hub.unregister("F")
        }
    }

    @Test
    fun `large flood conservation with newest last`() = runBlocking {
        val h = newHub(3)
        val scope = this

        val gate = CompletableDeferred<Unit>()
        val received = Collections.synchronizedList(mutableListOf<String>())
        h.hub.register("G", { text ->
            gate.await()
            received.add(text)
        }, scope)

        for (i in 1..20) h.hub.broadcastExcept(null, "m$i")
        gate.complete(Unit)
        drainUntilStable(received, 3)
        delay(50)

        try {
            val snapshot = synchronized(received) { received.toList() }
            val dropped = droppedCount(h.metrics.scrape())
            assertEquals(20.0, dropped + snapshot.size)
            assertEquals("m20", snapshot.last())
            // 送达序号严格递增
            assertEquals(snapshot, snapshot.sortedBy { it.removePrefix("m").toInt() })
            for (i in 1 until snapshot.size) {
                val prev = snapshot[i - 1].removePrefix("m").toInt()
                val curr = snapshot[i].removePrefix("m").toInt()
                assert(prev < curr) { "delivery order must be strictly increasing: $snapshot" }
            }
        } finally {
            h.hub.unregister("G")
        }
    }

    @Test
    fun `per-client drop isolation under shared flood`() = runBlocking {
        val scope = this

        val h1 = newHub(2)
        val gate1 = CompletableDeferred<Unit>()
        val received1 = Collections.synchronizedList(mutableListOf<String>())
        h1.hub.register("H1", { text ->
            gate1.await()
            received1.add(text)
        }, scope)

        for (i in 1..6) h1.hub.broadcastExcept(null, "m$i")
        gate1.complete(Unit)
        drainUntilStable(received1, 2)
        delay(50)

        val snap1 = synchronized(received1) { received1.toList() }
        val dropped1 = droppedCount(h1.metrics.scrape())
        assertEquals(6.0, dropped1 + snap1.size)
        assertEquals(4.0, dropped1)
        assertEquals(listOf("m5", "m6"), snap1)

        val h2 = newHub(4)
        val gate2 = CompletableDeferred<Unit>()
        val received2 = Collections.synchronizedList(mutableListOf<String>())
        h2.hub.register("H2", { text ->
            gate2.await()
            received2.add(text)
        }, scope)

        for (i in 1..6) h2.hub.broadcastExcept(null, "m$i")
        gate2.complete(Unit)
        drainUntilStable(received2, 4)
        delay(50)

        try {
            val snap2 = synchronized(received2) { received2.toList() }
            val dropped2 = droppedCount(h2.metrics.scrape())
            assertEquals(6.0, dropped2 + snap2.size)
            assertEquals(2.0, dropped2)
            assertEquals(listOf("m3", "m4", "m5", "m6"), snap2)
        } finally {
            h1.hub.unregister("H1")
            h2.hub.unregister("H2")
        }
    }
}
