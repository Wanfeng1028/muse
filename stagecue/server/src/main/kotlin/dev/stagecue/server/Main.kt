package dev.stagecue.server

import dev.stagecue.server.config.ServerConfig
import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.server.ratelimit.RateLimitSettings
import dev.stagecue.server.ratelimit.RateLimiting
import dev.stagecue.server.ratelimit.TokenBucketLimiter
import dev.stagecue.server.ws.BroadcastHub
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.Application
import io.ktor.server.application.install
import io.ktor.server.cio.CIO
import io.ktor.server.engine.embeddedServer
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.plugins.callid.CallId
import io.ktor.server.plugins.callid.callId
import io.ktor.server.plugins.calllogging.CallLogging
import io.ktor.server.request.httpMethod
import io.ktor.server.request.uri
import io.ktor.server.websocket.WebSockets
import kotlinx.serialization.json.Json
import org.slf4j.LoggerFactory
import org.slf4j.event.Level
import java.util.UUID

private val log = LoggerFactory.getLogger("dev.stagecue.server.Main")

fun main() {
    val config = ServerConfig.fromEnv().validateOrExit()

    val ds = Database.init(config.dataDir)
    val store = SqliteShowStore(ds)
    val settings = SettingsStore(ds)
    val hub = SyncHub(settings = settings)
    val metrics = StageMetrics()
    metrics.dbMigrationsApplied(Database.lastMigrationsApplied)

    val server = embeddedServer(CIO, port = config.port, host = config.host) {
        module(
            store, hub, settings, metrics,
            rateLimit = RateLimitSettings(config.rateLimitRps, config.rateLimitBurst),
            readiness = {
                try {
                    settings.getBoolean("rehearsal", false)
                    true
                } catch (e: Exception) {
                    log.warn("readiness 检查失败", e)
                    false
                }
            },
        )
    }

    Runtime.getRuntime().addShutdownHook(Thread {
        log.info("Shutdown hook triggered, stopping server gracefully")
        server.stop(1000, 3000)
        try {
            store.close()
        } catch (e: Exception) {
            log.warn("Failed to close ShowStore", e)
        }
        try {
            settings.close()
        } catch (e: Exception) {
            log.warn("Failed to close SettingsStore", e)
        }
    })

    val dbFile = config.dataDir.resolve("stagecue.db").absolutePath
    log.info(
        "StageCue server starting on {}:{} (data dir: {}, db: {}, logLevel: {})",
        config.host,
        config.port,
        config.dataDir.absolutePath,
        dbFile,
        config.logLevel,
    )
    server.start(wait = true)
}

fun Application.module(
    store: SqliteShowStore,
    hub: SyncHub,
    settings: SettingsStore,
    metrics: StageMetrics = StageMetrics(),
    rateLimit: RateLimitSettings = RateLimitSettings(),
    readiness: () -> Boolean = { true },
) {
    install(WebSockets) {
        pingPeriodMillis = 15_000
        timeoutMillis = 30_000
        maxFrameSize = Long.MAX_VALUE
        masking = false
    }

    install(ContentNegotiation) {
        json(Json {
            prettyPrint = true
            ignoreUnknownKeys = true
            encodeDefaults = true
        })
    }

    install(CallId) {
        header("X-Request-Id")
        generate { UUID.randomUUID().toString() }
        verify { it.isNotBlank() }
    }

    install(CallLogging) {
        level = Level.INFO
        format { call ->
            val id = call.callId ?: "-"
            "[$id] ${call.request.httpMethod.value} ${call.request.uri}"
        }
        mdc("call-id") { it.callId ?: "-" }
    }

    install(RateLimiting) {
        limiter = TokenBucketLimiter(rateLimit.rps.toDouble(), rateLimit.burst, rateLimit.clock)
        onRejected = { metrics.httpRateLimited() }
    }

    val broadcaster = BroadcastHub(metrics)

    configureRoutes(store, hub, metrics, broadcaster, readiness)
}
