package dev.stagecue.server

import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.server.ws.BroadcastHub
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.util.Collections

class BroadcastHubBackpressureDeepTest {

    private fun newHub(capacity: Int = 2): Pair<BroadcastHub, StageMetrics> {
        val metrics = StageMetrics()
        return BroadcastHub(metrics, capacity) to metrics
    }

    private fun droppedCount(scrape: String): Double =
        Regex("""stagecue_ws_broadcast_dropped_total ([0-9.]+)""")
            .find(scrape)!!.groupValues[1].toDouble()

    private suspend fun drainUntilStable(received: MutableList<String>) {
        withTimeout(5000) { while (received.isEmpty()) delay(50) }
        withTimeout(5000) {
            var last = -1
            while (true) {
                delay(100)
                if (received.size == last) break
                last = received.size
            }
        }
    }

    private fun assertStrictlyIncreasing(values: List<Int>) {
        for (i in 1 until values.size) {
            assertTrue(values[i] > values[i - 1], "送达序列必须严格递增：$values")
        }
    }

    @Test
    fun `capacity one slow consumer keeps only newest`() {
        val (hub, metrics) = newHub(1)
        val received = Collections.synchronizedList(mutableListOf<String>())
        val gate = CompletableDeferred<Unit>()
        runBlocking {
            hub.register(
                "slow",
                BroadcastHub.FrameSink { t ->
                    gate.await()
                    received.add(t)
                },
                this
            )
            hub.broadcastExcept(null, "m1")
            hub.broadcastExcept(null, "m2")
            hub.broadcastExcept(null, "m3")
            gate.complete(Unit)
            drainUntilStable(received)
            hub.unregister("slow")
        }
        assertEquals("m3", received.last())
        val dropped = droppedCount(metrics.scrape())
        assertEquals(3.0, dropped + received.size.toDouble())
        val seqs = received.map { it.removePrefix("m").toInt() }
        assertStrictlyIncreasing(seqs)
    }

    @Test
    fun `flood drops counted precisely`() {
        val (hub, metrics) = newHub(2)
        val received = Collections.synchronizedList(mutableListOf<String>())
        val gate = CompletableDeferred<Unit>()
        runBlocking {
            hub.register(
                "slow",
                BroadcastHub.FrameSink { t ->
                    gate.await()
                    received.add(t)
                },
                this
            )
            repeat(10) { i -> hub.broadcastExcept(null, "m${i + 1}") }
            gate.complete(Unit)
            drainUntilStable(received)
            hub.unregister("slow")
        }
        val dropped = droppedCount(metrics.scrape())
        assertEquals(10.0, dropped + received.size.toDouble())
        assertTrue(dropped > 0.0, "洪水下丢弃数应大于 0，实际 $dropped")
        assertEquals("m10", received.last())
        val seqs = received.map { it.removePrefix("m").toInt() }
        assertStrictlyIncreasing(seqs)
    }

@Test
    fun `slow consumer does not starve fast consumer`() {
        val (hub, metrics) = newHub(2)
        val slowReceived = Collections.synchronizedList(mutableListOf<String>())
        val fastReceived = Collections.synchronizedList(mutableListOf<String>())
        val gate = CompletableDeferred<Unit>()
        runBlocking {
            hub.register(
                "slow",
                BroadcastHub.FrameSink { t ->
                    gate.await()
                    slowReceived.add(t)
                },
                this
            )
            val beforeSlow = droppedCount(metrics.scrape())
            hub.register(
                "fast",
                BroadcastHub.FrameSink { t -> fastReceived.add(t) },
                this
            )
            repeat(5) { i ->
                hub.broadcastExcept(null, "m${i + 1}")
                yield()
            }
            drainUntilStable(fastReceived)
            gate.complete(Unit)
            drainUntilStable(slowReceived)
            val afterSlow = droppedCount(metrics.scrape())
            hub.unregister("slow")
            hub.unregister("fast")
            assertEquals(listOf("m1", "m2", "m3", "m4", "m5"), fastReceived.toList())
            val slowDropped = afterSlow - beforeSlow
            assertEquals(5.0, slowDropped + slowReceived.size.toDouble())
            val seqs = slowReceived.map { it.removePrefix("m").toInt() }
            assertStrictlyIncreasing(seqs)
            if (slowReceived.isNotEmpty()) {
                assertEquals("m5", slowReceived.last())
            }
        }
    }

    @Test
    fun `excluded client receives nothing under flood`() {
        val (hub, _) = newHub(2)
        val xReceived = Collections.synchronizedList(mutableListOf<String>())
        runBlocking {
            hub.register("x", BroadcastHub.FrameSink { t -> xReceived.add(t) }, this)
            repeat(5) { i -> hub.broadcastExcept("x", "m${i + 1}") }
            delay(300)
            hub.unregister("x")
        }
        assertTrue(xReceived.isEmpty(), "被排除的 client 不应收到任何消息，实际 $xReceived")
    }

    @Test
    fun `unregister during backpressure stops delivery`() {
        val (hub, _) = newHub(2)
        val received = Collections.synchronizedList(mutableListOf<String>())
        val gate = CompletableDeferred<Unit>()
        runBlocking {
            hub.register(
                "slow",
                BroadcastHub.FrameSink { t ->
                    gate.await()
                    received.add(t)
                },
                this
            )
            hub.broadcastExcept(null, "m1")
            hub.broadcastExcept(null, "m2")
            hub.broadcastExcept(null, "m3")
            hub.unregister("slow")
            gate.complete(Unit)
            delay(300)
            hub.broadcastExcept(null, "after")
            delay(300)
        }
        assertEquals(0, hub.sessionCount())
        assertTrue(!received.contains("after"), "注销后不应再收到新消息，实际 $received")
    }
}
