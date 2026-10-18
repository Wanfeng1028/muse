package dev.stagecue.shared.sync

import dev.stagecue.shared.oplog.InMemoryOpLogStore
import kotlin.test.*

class SharedSyncEdgeDeepTest {

    // ---------- ClockEstimator ----------

    @Test
    fun resetClearsSamples() {
        val est = ClockEstimator()
        // 三个足够样本，让 estimatedOffsetMs 非空
        est.addSample(0, 10, 10, 30)
        est.addSample(0, 20, 20, 60)
        est.addSample(0, 5, 5, 25)
        assertNotNull(est.estimatedOffsetMs())

        est.reset()

        assertNull(est.estimatedOffsetMs())
        assertEquals(0, est.sampleCount())
    }

    @Test
    fun sampleCountTracksAdds() {
        val est = ClockEstimator()
        est.addSample(0, 10, 10, 30)
        assertEquals(1, est.sampleCount())
        est.addSample(0, 20, 20, 60)
        assertEquals(2, est.sampleCount())
    }

    @Test
    fun serverNowMsNullWhenInsufficient() {
        val est = ClockEstimator()
        // 只加 2 个样本，少于阈值 3
        est.addSample(0, 10, 10, 30)
        est.addSample(0, 20, 20, 60)
        assertNull(est.serverNowMs(1000L))
    }

    @Test
    fun exactThreePicksMinDelay() {
        val est = ClockEstimator()

        // 样本 A: t0=0, t1=100, t2=100, t3=1000
        //   delay  = (t3 - t0) - (t2 - t1) = (1000 - 0) - (100 - 100) = 1000 - 0 = 900
        //   offset = ((t1 - t0) + (t2 - t3)) / 2 = ((100 - 0) + (100 - 1000)) / 2 = (100 + (-900)) / 2 = -800 / 2 = -400
        est.addSample(0, 100, 100, 1000)

        // 样本 B: t0=0, t1=10, t2=10, t3=30
        //   delay  = (30 - 0) - (10 - 10) = 30 - 0 = 30
        //   offset = ((10 - 0) + (10 - 30)) / 2 = (10 + (-20)) / 2 = -10 / 2 = -5
        est.addSample(0, 10, 10, 30)

        // 样本 C: t0=0, t1=5, t2=5, t3=60
        //   delay  = (60 - 0) - (5 - 5) = 60 - 0 = 60
        //   offset = ((5 - 0) + (5 - 60)) / 2 = (5 + (-55)) / 2 = -50 / 2 = -25
        est.addSample(0, 5, 5, 60)

        // 最小 delay 是 B(30)，其 offset 为 -5
        assertEquals(-5L, est.estimatedOffsetMs())
    }

    // ---------- EventDeduper ----------

    @Test
    fun clearResets() {
        val deduper = EventDeduper()
        assertTrue(deduper.isNew("a"))
        assertEquals(1, deduper.size())

        deduper.clear()

        assertEquals(0, deduper.size())
        assertTrue(deduper.isNew("a"))
    }

    @Test
    fun capacityOneEvictsImmediately() {
        val deduper = EventDeduper(1)
        assertTrue(deduper.isNew("a"))
        // 加入 b 后窗口超过容量 1，a 被逐出 seen
        assertTrue(deduper.isNew("b"))
        // a 已被逐出，因此再次视为新事件
        assertTrue(deduper.isNew("a"))
    }

    @Test
    fun duplicateDoesNotGrowWindow() {
        val deduper = EventDeduper()
        assertTrue(deduper.isNew("x"))
        assertFalse(deduper.isNew("x"))
        assertFalse(deduper.isNew("x"))
        assertEquals(1, deduper.size())
    }

    // ---------- InMemoryOpLogStore ----------

    @Test
    fun appendPreservesNullCueIdAndDetail() {
        val store = InMemoryOpLogStore()
        val entry = store.append("T", null, "d")
        assertNull(entry.cueId)
        assertEquals("d", entry.detail)
        assertEquals("T", entry.type)
    }

    @Test
    fun appendAtMsIsPositive() {
        val store = InMemoryOpLogStore()
        val entry = store.append("T", "cue-1", "detail")
        assertTrue(entry.atMs > 0)
    }

    @Test
    fun clearThenAppendRestartsSeqAndChangesEventId() {
        val store = InMemoryOpLogStore()
        val first = store.append("T1", null, "d1")
        store.append("T2", null, "d2")

        store.clear()
        assertTrue(store.readAll().isEmpty())

        val afterClear = store.append("T3", null, "d3")
        assertEquals(1L, afterClear.seq)
        assertNotEquals(first.eventId, afterClear.eventId)
    }
}
