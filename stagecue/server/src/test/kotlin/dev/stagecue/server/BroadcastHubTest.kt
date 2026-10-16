package dev.stagecue.server

import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.server.ws.BroadcastHub
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Test

class BroadcastHubTest {

    private fun newHub(capacity: Int = 2): Pair<BroadcastHub, StageMetrics> {
        val metrics = StageMetrics()
        return BroadcastHub(metrics, capacity) to metrics
    }

    @Test
    fun `slow consumer drops oldest and counts drops`() {
        val (hub, metrics) = newHub(2)
        val received = java.util.Collections.synchronizedList(mutableListOf<String>())
        runBlocking {
            hub.register("slow", BroadcastHub.FrameSink { t -> received.add(t) }, this)
            repeat(5) { i -> hub.broadcastExcept(null, "m${i + 1}") }
            withTimeout(5000) { while (received.isEmpty()) delay(50) }
            // 等到发送协程排空队列（连续 100ms 无新投递即视为排空）
            withTimeout(5000) {
                var last = -1
                while (true) {
                    delay(100)
                    if (received.size == last) break
                    last = received.size
                }
            }
            hub.unregister("slow")
        }
        // DROP_OLDEST 不变量：最新的 m5 一定送达；丢弃数 + 送达数 == 广播总数 5；送达保序
        assertEquals("m5", received.last())
        val dropped = Regex("""stagecue_ws_broadcast_dropped_total ([0-9.]+)""")
            .find(metrics.scrape())!!.groupValues[1].toDouble()
        assertEquals(5.0, dropped + received.size.toDouble())
        assertEquals(received.sorted(), received)
    }

    @Test
    fun `broadcastExcept skips excluded client`() {
        val (hub, _) = newHub()
        val receivedA = java.util.Collections.synchronizedList(mutableListOf<String>())
        val receivedB = java.util.Collections.synchronizedList(mutableListOf<String>())
        runBlocking {
            hub.register("a", BroadcastHub.FrameSink { t -> receivedA.add(t) }, this)
            hub.register("b", BroadcastHub.FrameSink { t -> receivedB.add(t) }, this)
            hub.broadcastExcept("a", "hi")
            withTimeout(5000) { while (receivedB.isEmpty()) delay(50) }
            hub.unregister("a")
            hub.unregister("b")
        }
        assertEquals(listOf("hi"), receivedB)
        assertFalse(receivedA.contains("hi"))
    }

    @Test
    fun `unregister is idempotent and re-register replaces`() {
        val (hub, _) = newHub()
        hub.unregister("nope")
        runBlocking {
            hub.register("x", BroadcastHub.FrameSink { }, this)
            hub.register("x", BroadcastHub.FrameSink { }, this)
            assertEquals(1, hub.sessionCount())
            hub.unregister("x")
            hub.unregister("x")
            assertEquals(0, hub.sessionCount())
        }
    }

    @Test
    fun `sink failure unregisters client`() {
        val (hub, _) = newHub()
        runBlocking {
            hub.register("bad", BroadcastHub.FrameSink { throw RuntimeException("boom") }, this)
            hub.broadcastExcept(null, "x")
            withTimeout(5000) { while (hub.sessionCount() != 0) delay(50) }
        }
        assertEquals(0, hub.sessionCount())
    }
}
