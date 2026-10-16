package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.server.ratelimit.RateLimitSettings
import dev.stagecue.server.ratelimit.TokenBucketLimiter
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class TokenBucketTest {

    @Test
    fun `bucket allows burst then rejects with retryAfter`() {
        var now = 0L
        val l = TokenBucketLimiter(1.0, 2) { now }
        assertTrue(l.tryAcquire("k").allowed)
        assertTrue(l.tryAcquire("k").allowed)
        val third = l.tryAcquire("k")
        assertFalse(third.allowed)
        assertTrue(third.retryAfterMs > 0)
    }

    @Test
    fun `buckets are isolated per key`() {
        var now = 0L
        val l = TokenBucketLimiter(1.0, 2) { now }
        assertTrue(l.tryAcquire("a").allowed)
        assertTrue(l.tryAcquire("a").allowed)
        assertFalse(l.tryAcquire("a").allowed)
        assertTrue(l.tryAcquire("b").allowed)
    }

    @Test
    fun `tokens refill over time`() {
        var now = 0L
        val l = TokenBucketLimiter(1.0, 2) { now }
        assertTrue(l.tryAcquire("k").allowed)
        assertTrue(l.tryAcquire("k").allowed)
        assertFalse(l.tryAcquire("k").allowed)
        now += 1_000_000_000L
        assertTrue(l.tryAcquire("k").allowed)
    }
}

class RateLimitRouteTest {

    @TempDir
    lateinit var tempDir: File

    @Test
    fun `exceeding burst returns 429 with Retry-After`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(settings = settings)
        val metrics = StageMetrics()
        var now = 0L
        application {
            module(store, hub, settings, metrics, rateLimit = RateLimitSettings(rps = 1, burst = 2, clock = { now }))
        }
        val client = createClient { }
        val r1 = client.get("/api/show")
        val r2 = client.get("/api/show")
        val r3 = client.get("/api/show")
        assertEquals(HttpStatusCode.OK, r1.status)
        assertEquals(HttpStatusCode.OK, r2.status)
        assertEquals(HttpStatusCode.TooManyRequests, r3.status)
        assertNotNull(r3.headers["Retry-After"])
        assertTrue(r3.bodyAsText().contains("rate_limited"))
    }

    @Test
    fun `probes are exempt from rate limiting`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(settings = settings)
        val metrics = StageMetrics()
        var now = 0L
        application {
            module(store, hub, settings, metrics, rateLimit = RateLimitSettings(rps = 1, burst = 2, clock = { now }))
        }
        val client = createClient { }
        client.get("/api/show")
        client.get("/api/show")
        val third = client.get("/api/show")
        assertEquals(HttpStatusCode.TooManyRequests, third.status)
        assertEquals(HttpStatusCode.OK, client.get("/healthz").status)
        assertEquals(HttpStatusCode.OK, client.get("/readyz").status)
        assertEquals(HttpStatusCode.OK, client.get("/metrics").status)
    }

    @Test
    fun `rejected requests increment metric`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(settings = settings)
        val metrics = StageMetrics()
        var now = 0L
        application {
            module(store, hub, settings, metrics, rateLimit = RateLimitSettings(rps = 1, burst = 2, clock = { now }))
        }
        val client = createClient { }
        client.get("/api/show")
        client.get("/api/show")
        client.get("/api/show")
        val body = client.get("/metrics").bodyAsText()
        assertTrue(body.contains("stagecue_http_rate_limited_total 1.0"))
    }
}
