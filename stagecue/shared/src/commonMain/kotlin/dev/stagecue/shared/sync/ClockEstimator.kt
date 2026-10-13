package dev.stagecue.shared.sync

/**
 * NTP-like clock offset estimator using the minimum-delay sample heuristic.
 *
 * For each round-trip:
 *   t0 = client send time
 *   t1 = server receive time
 *   t2 = server send time
 *   t3 = client receive time
 *
 *   delay  = (t3 - t0) - (t2 - t1)
 *   offset = ((t1 - t0) + (t2 - t3)) / 2
 */
class ClockEstimator {

    private data class Sample(
        val delayMs: Long,
        val offsetMs: Long
    )

    private val samples = ArrayList<Sample>()

    @Synchronized
    fun addSample(t0: Long, t1: Long, t2: Long, t3: Long) {
        val delay = (t3 - t0) - (t2 - t1)
        val offset = ((t1 - t0) + (t2 - t3)) / 2
        samples.add(Sample(delayMs = delay, offsetMs = offset))
    }

    @Synchronized
    fun estimatedOffsetMs(): Long? {
        if (samples.size < 3) return null
        val best = samples.minByOrNull { it.delayMs } ?: return null
        return best.offsetMs
    }

    @Synchronized
    fun serverNowMs(clientNowMs: Long): Long? {
        val offset = estimatedOffsetMs() ?: return null
        return clientNowMs + offset
    }

    @Synchronized
    fun sampleCount(): Int = samples.size

    @Synchronized
    fun reset() {
        samples.clear()
    }
}
