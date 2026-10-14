package dev.stagecue.server

import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.shared.protocol.*
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.*
import io.ktor.server.response.respond
import io.ktor.server.response.respondText
import io.ktor.server.routing.*
import io.ktor.server.websocket.*
import io.ktor.websocket.*
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

fun Application.configureRoutes(store: SqliteShowStore, hub: SyncHub, metrics: StageMetrics) {
    // clientId -> 会话，用于 cue 事件广播
    val sessions = ConcurrentHashMap<String, WebSocketServerSession>()

    suspend fun broadcastExcept(exceptClientId: String?, message: WsMessage) {
        val text = WsJson.json.encodeToString(WsMessage.serializer(), message)
        for ((id, sess) in sessions) {
            if (id == exceptClientId) continue
            try {
                sess.send(Frame.Text(text))
            } catch (e: Exception) {
                sessions.remove(id)
            }
        }
    }

    routing {
        get("/healthz") {
            call.respondText("{\"status\":\"ok\"}")
        }

        get("/metrics") {
            call.respondText(
                metrics.scrape(),
                ContentType.parse("text/plain; version=0.0.4; charset=utf-8")
            )
        }

        get("/api/show") {
            metrics.showRequested()
            call.respond(HttpStatusCode.OK, store.getShow())
        }

        get("/api/rehearsal") {
            call.respond(HttpStatusCode.OK, mapOf("rehearsal" to hub.rehearsalMode))
        }

        webSocket("/ws") {
            var myClientId: String? = null
            try {
            for (frame in incoming) {
                if (frame !is Frame.Text) continue
                val text = frame.readText()
                val msg = try {
                    WsJson.json.decodeFromString(WsMessage.serializer(), text)
                } catch (e: Exception) {
                    val err = Error(
                        msgId = UUID.randomUUID().toString(),
                        sentAtMs = System.currentTimeMillis(),
                        code = "PARSE_ERROR",
                        message = e.message ?: "parse error",
                    )
                    send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), err)))
                    continue
                }

                when (msg) {
                    is Hello -> {
                        if (msg.clientId.isBlank()) {
                            val err = Error(
                                msgId = UUID.randomUUID().toString(),
                                sentAtMs = System.currentTimeMillis(),
                                code = "INVALID_CLIENT_ID",
                                message = "clientId must not be blank",
                            )
                            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), err)))
                            continue
                        }
                        myClientId = msg.clientId
                        sessions[msg.clientId] = this
                        metrics.wsConnected()
                        val welcome = hub.handleConnect(msg.clientId, msg.role)
                        send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), welcome)))
                    }
                    is ClockPing -> {
                        val pong = hub.handleClockPing(msg)
                        send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), pong)))
                    }
                    is TriggerCue -> {
                        val out = hub.handleTriggerCue(msg)
                        if (out is CueFired) metrics.cueTriggered(rehearsal = out.rehearsal)
                        send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), out)))
                        // 广播给其他客户端（触发者已收到直接回执）
                        if (out is CueFired) {
                            broadcastExcept(myClientId, out)
                        }
                    }
                    is ArmCue -> {
                        val out = hub.handleArmCue(msg)
                        metrics.cueArmed()
                        send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), out)))
                        broadcastExcept(myClientId, out)
                    }
                    is SetRehearsal -> {
                        val changed = hub.setRehearsal(msg.enabled)
                        send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), changed)))
                        broadcastExcept(myClientId, changed)
                    }
                    else -> {
                        val out = hub.handleUnknown(msg)
                        send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), out)))
                    }
                }
            }
            } finally {
                myClientId?.let {
                    sessions.remove(it)
                    metrics.wsDisconnected()
                }
            }
        }
    }
}
