package dev.stagecue.server.ratelimit

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class TokenBucketDeepTest {

    @Test
    fun `init rejects zero rps`() {
        // init { require(rps > 0.0) }  => rps=0.0 触发 IllegalArgumentException
        assertThrows(IllegalArgumentException::class.java) {
            TokenBucketLimiter(rps = 0.0, burst = 5)
        }
    }

    @Test
    fun `init rejects negative rps`() {
        // require(rps > 0.0) => -1.0 不满足
        assertThrows(IllegalArgumentException::class.java) {
            TokenBucketLimiter(rps = -1.0, burst = 5)
        }
    }

    @Test
    fun `init rejects zero burst`() {
        // require(burst >= 1) => 0 不满足
        assertThrows(IllegalArgumentException::class.java) {
            TokenBucketLimiter(rps = 10.0, burst = 0)
        }
    }

    @Test
    fun `burst of one allows exactly one then denies`() {
        // burst=1：初始 tokens=1.0；时钟冻结 => elapsedSec=0 => 不补充
        var nowNs = 0L
        val limiter = TokenBucketLimiter(rps = 10.0, burst = 1, clock = { nowNs })

        val first = limiter.tryAcquire("k")
        assertEquals(true, first.allowed)
        assertEquals(0L, first.retryAfterMs)

        // tokens=0.0 < 1 => denied；retryAfterMs = ceil((1-0)*1000/10) = ceil(100.0) = 100
        val second = limiter.tryAcquire("k")
        assertEquals(false, second.allowed)
        assertEquals(100L, second.retryAfterMs)
    }

    @Test
    fun `retryAfterMs exact formula`() {
        // rps=2.0：retryAfterMs = ceil((1.0 - tokens) * 1000.0 / rps)
        var nowNs = 0L
        val limiter = TokenBucketLimiter(rps = 2.0, burst = 1, clock = { nowNs })

        assertTrue(limiter.tryAcquire("k").allowed)

        // tokens=0.0 => ceil(1.0*1000/2.0) = ceil(500.0) = 500
        val denied = limiter.tryAcquire("k")
        assertFalse(denied.allowed)
        assertEquals(500L, denied.retryAfterMs)
    }

    @Test
    fun `partial refill allows after exact wait`() {
        var nowNs = 0L
        val limiter = TokenBucketLimiter(rps = 2.0, burst = 1, clock = { nowNs })

        assertTrue(limiter.tryAcquire("k").allowed)
        assertFalse(limiter.tryAcquire("k").allowed)

        // 推进 250ms => elapsedSec=0.25 => tokens = min(1.0, 0 + 0.25*2) = 0.5 < 1 => denied
        nowNs = 250_000_000L
        val at250 = limiter.tryAcquire("k")
        assertFalse(at250.allowed)
        // retryAfterMs = ceil((1.0 - 0.5)*1000/2.0) = ceil(250.0) = 250
        assertEquals(250L, at250.retryAfterMs)

        // 推进到 500ms => elapsedSec=0.5 => tokens = min(1.0, 0.5 + 0.5*2) = 1.0 => allowed
        nowNs = 500_000_000L
        val at500 = limiter.tryAcquire("k")
        assertTrue(at500.allowed)
        assertEquals(0L, at500.retryAfterMs)
    }

    @Test
    fun `tokens capped at burst after long idle`() {
        var nowNs = 0L
        val limiter = TokenBucketLimiter(rps = 10.0, burst = 3, clock = { nowNs })

        assertTrue(limiter.tryAcquire("k").allowed)
        assertTrue(limiter.tryAcquire("k").allowed)
        assertTrue(limiter.tryAcquire("k").allowed)
        assertFalse(limiter.tryAcquire("k").allowed)

        // 推进 1 小时 => 理论上补充 10*3600=36000 tokens，但 min(burst, ...) 封顶为 3.0
        nowNs = 3_600_000_000_000L

        assertTrue(limiter.tryAcquire("k").allowed)
        assertTrue(limiter.tryAcquire("k").allowed)
        assertTrue(limiter.tryAcquire("k").allowed)
        // 封顶 3 个已耗尽 => 第 4 次 denied
        assertFalse(limiter.tryAcquire("k").allowed)
    }

    @Test
    fun `backward clock does not grant extra tokens`() {
        var nowNs = 1_000_000_000L
        val limiter = TokenBucketLimiter(rps = 1.0, burst = 1, clock = { nowNs })

        assertTrue(limiter.tryAcquire("k").allowed)
        assertFalse(limiter.tryAcquire("k").allowed)

        // 时钟倒退：now=0，bucket.lastRefillNs=1_000_000_000 => (now - last) 为负 => coerceAtLeast(0) = 0
        nowNs = 0L
        val denied = limiter.tryAcquire("k")
        assertFalse(denied.allowed)
        // tokens 仍为 0 => ceil((1.0-0.0)*1000/1.0)=1000，且 coerceAtLeast(1L) 保证 >= 1
        assertTrue(denied.retryAfterMs >= 1L)
    }

    @Test
    fun `many keys do not interfere`() {
        var nowNs = 0L
        val limiter = TokenBucketLimiter(rps = 1.0, burst = 1, clock = { nowNs })

        assertTrue(limiter.tryAcquire("a").allowed)
        assertFalse(limiter.tryAcquire("a").allowed)

        // 不同 key 有独立 bucket：首次访问 tokens=burst=1.0 => allowed
        assertTrue(limiter.tryAcquire("b").allowed)
        assertFalse(limiter.tryAcquire("b").allowed)
    }
}
