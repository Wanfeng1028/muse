package dev.stagecue.server

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
import java.io.File
import java.util.UUID
import kotlin.time.Duration.Companion.seconds

private val log = LoggerFactory.getLogger("dev.stagecue.server.Main")

fun main() {
    val port = System.getenv("STAGECUE_PORT")?.toIntOrNull() ?: 8080
    if (System.getenv("STAGECUE_PORT") == null) {
        log.info("STAGECUE_PORT not set, defaulting to {}", port)
    }

    val dataDirPath = System.getenv("STAGECUE_DATA_DIR") ?: "./data"
    if (System.getenv("STAGECUE_DATA_DIR") == null) {
        log.info("STAGECUE_DATA_DIR not set, defaulting to {}", dataDirPath)
    }
    val dataDir = File(dataDirPath)
    if (!dataDir.exists()) {
        dataDir.mkdirs()
    }

    val store = ShowStore(dataDir)
    val hub = SyncHub()

    val server = embeddedServer(CIO, port = port, host = "0.0.0.0") {
        module(store, hub)
    }

    Runtime.getRuntime().addShutdownHook(Thread {
        log.info("Shutdown hook triggered, stopping server gracefully")
        server.stop(1000, 3000)
    })

    log.info("StageCue server starting on port {} (data dir: {})", port, dataDir.absolutePath)
    server.start(wait = true)
}

fun Application.module(store: ShowStore, hub: SyncHub) {
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

    configureRoutes(store, hub)
}
