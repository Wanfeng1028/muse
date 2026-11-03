package dev.stagecue.shared.sync

import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.Test

class ClockEstimatorTest {

    @Test
    fun returnsNullWhenInsufficientSamples() {
        val est = ClockEstimator()
        assertNull(est.estimatedOffsetMs())
        est.addSample(t0 = 1000, t1 = 1000, t2 = 1000, t3 = 1000)
        assertNull(est.estimatedOffsetMs())
        est.addSample(t0 = 1000, t1 = 1000, t2 = 1000, t3 = 1000)
        assertNull(est.estimatedOffsetMs())
        est.addSample(t0 = 1000, t1 = 1000, t2 = 1000, t3 = 1000)
        assertNotNull(est.estimatedOffsetMs())
    }

    @Test
    fun computesKnownOffsetWithMinDelay() {
        val est = ClockEstimator()
        // offset = ((t1-t0) + (t2-t3)) / 2, delay = (t3-t0) - (t2-t1)
        // Case A: high delay (400), offset 100
        est.addSample(t0 = 0, t1 = 300, t2 = 300, t3 = 400)
        // Case B: medium delay (200), offset 100
        est.addSample(t0 = 0, t1 = 200, t2 = 200, t3 = 200)
        // Case C: min delay (20), offset 100 (server 100ms ahead)
        est.addSample(t0 = 0, t1 = 110, t2 = 110, t3 = 20)

        val offset = est.estimatedOffsetMs()
        assertEquals(100L, offset)
    }

    @Test
    fun picksMinimumDelaySample() {
        val est = ClockEstimator()
        // sample with offset 50 but high delay (400)
        est.addSample(t0 = 0, t1 = 250, t2 = 250, t3 = 400)
        // sample with offset 70 and min delay (20)
        est.addSample(t0 = 0, t1 = 80, t2 = 80, t3 = 20)
        // sample with offset 60 and medium delay (200)
        est.addSample(t0 = 0, t1 = 160, t2 = 160, t3 = 200)

        assertEquals(70L, est.estimatedOffsetMs())
    }

    @Test
    fun serverNowUsesOffset() {
        val est = ClockEstimator()
        est.addSample(t0 = 0, t1 = 110, t2 = 110, t3 = 20)
        est.addSample(t0 = 0, t1 = 110, t2 = 110, t3 = 20)
        est.addSample(t0 = 0, t1 = 110, t2 = 110, t3 = 20)
        assertEquals(1_100L, est.serverNowMs(1_000L))
    }

    @Test
    fun negativeOffsetSupported() {
        val est = ClockEstimator()
        // server is 30ms behind client
        est.addSample(t0 = 0, t1 = -20, t2 = -20, t3 = 20)
        est.addSample(t0 = 0, t1 = -20, t2 = -20, t3 = 20)
        est.addSample(t0 = 0, t1 = -20, t2 = -20, t3 = 20)
        assertEquals(-30L, est.estimatedOffsetMs())
    }
}
