package dev.stagecue.server.ratelimit

import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.server.response.respondText
import io.ktor.server.application.ApplicationCall
import io.ktor.server.application.createApplicationPlugin
import io.ktor.server.request.uri
import io.ktor.server.response.respond

/** module() 传入的限流档位（由 ServerConfig 的环境变量换算而来，便于测试直接构造）。 */
data class RateLimitSettings(
    val rps: Int = 60,
    val burst: Int = 120,
    val clock: () -> Long = { System.nanoTime() },
)

class RateLimitingConfig {
    var limiter: TokenBucketLimiter = TokenBucketLimiter(60.0, 120)
    var exemptPaths: Set<String> = setOf("/healthz", "/readyz", "/metrics")
    var keyExtractor: (ApplicationCall) -> String = { it.request.local.remoteHost }
    var onRejected: (suspend (ApplicationCall) -> Unit)? = null
}

val RateLimiting = createApplicationPlugin("RateLimiting", ::RateLimitingConfig) {
    val cfg = pluginConfig
    onCall { call ->
        val path = call.request.uri.substringBefore("?")
        if (path in cfg.exemptPaths) return@onCall
        val result = cfg.limiter.tryAcquire(cfg.keyExtractor(call))
        if (!result.allowed) {
            val retrySec = ((result.retryAfterMs + 999) / 1000).coerceAtLeast(1)
            call.response.headers.append("Retry-After", retrySec.toString())
            cfg.onRejected?.invoke(call)
            call.respondText(
                text = "{\"error\":\"rate_limited\",\"retry_after_seconds\":$retrySec}",
                contentType = ContentType.Application.Json,
                status = HttpStatusCode.TooManyRequests,
            )
            // 不调 proceed：pipeline 在此停止，路由不会执行（已实测）
        }
    }
}
