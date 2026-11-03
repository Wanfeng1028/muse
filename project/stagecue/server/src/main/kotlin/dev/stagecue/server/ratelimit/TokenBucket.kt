package dev.stagecue.server.ratelimit

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.ceil
import kotlin.math.min

data class AcquireResult(val allowed: Boolean, val retryAfterMs: Long)

class TokenBucketLimiter(
    val rps: Double,
    val burst: Int,
    private val clock: () -> Long = { System.nanoTime() },
) {
    private data class Bucket(var tokens: Double, var lastRefillNs: Long)

    private val buckets = ConcurrentHashMap<String, Bucket>()

    init {
        require(rps > 0.0) { "rps must be > 0" }
        require(burst >= 1) { "burst must be >= 1" }
    }

    fun tryAcquire(key: String): AcquireResult {
        val bucket = buckets.computeIfAbsent(key) {
            Bucket(burst.toDouble(), clock())
        }
        synchronized(bucket) {
            val now = clock()
            val elapsedSec = (now - bucket.lastRefillNs).coerceAtLeast(0L) / 1_000_000_000.0
            bucket.tokens = min(burst.toDouble(), bucket.tokens + elapsedSec * rps)
            bucket.lastRefillNs = now
            return if (bucket.tokens >= 1.0) {
                bucket.tokens -= 1.0
                AcquireResult(true, 0L)
            } else {
                val retryAfterMs = ceil((1.0 - bucket.tokens) * 1000.0 / rps).toLong().coerceAtLeast(1L)
                AcquireResult(false, retryAfterMs)
            }
        }
    }
}
