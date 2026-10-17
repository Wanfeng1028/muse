package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.shared.protocol.*
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.server.testing.testApplication
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class WsRouteTest {
    @TempDir
    lateinit var tempDir: File

    @Test
    fun `malformed text frame yields PARSE_ERROR`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            send(Frame.Text("this is not json{{{"))
            val reply = (incoming.receive() as Frame.Text).readText()
            val msg = WsJson.json.decodeFromString(WsMessage.serializer(), reply)
            assertTrue(msg is Error, "expected Error, got: $reply")
            assertEquals("PARSE_ERROR", (msg as Error).code)
        }
    }

    @Test
    fun `blank clientId yields INVALID_CLIENT_ID`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val hello = Hello(
                msgId = "h-blank",
                sentAtMs = 1L,
                clientId = "",
                role = ClientRole.DIRECTOR,
                clientTimeMs = 1L,
            )
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello)))
            val reply = (incoming.receive() as Frame.Text).readText()
            val msg = WsJson.json.decodeFromString(WsMessage.serializer(), reply)
            assertTrue(msg is Error, "expected Error, got: $reply")
            assertEquals("INVALID_CLIENT_ID", (msg as Error).code)
            assertEquals("clientId must not be blank", msg.message)
        }
    }

    @Test
    fun `clock ping before hello returns pong with echoed seq and time`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val ping = ClockPing(msgId = "p1", sentAtMs = 1L, seq = 7L, clientTimeMs = 123L)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), ping)))
            val reply = (incoming.receive() as Frame.Text).readText()
            val msg = WsJson.json.decodeFromString(WsMessage.serializer(), reply)
            assertTrue(msg is ClockPong, "expected ClockPong, got: $reply")
            val pong = msg as ClockPong
            assertEquals(7L, pong.seq)
            assertEquals(123L, pong.clientTimeMs)
        }
    }

    @Test
    fun `trigger before hello is allowed with null role`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val trig = TriggerCue(msgId = "t1", sentAtMs = 1L, cueId = "cue-001")
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), trig)))
            val reply = (incoming.receive() as Frame.Text).readText()
            val msg = WsJson.json.decodeFromString(WsMessage.serializer(), reply)
            assertTrue(msg is CueFired, "expected CueFired, got: $reply")
            assertEquals("cue-001", (msg as CueFired).cueId)
        }
    }

    @Test
    fun `server-bound cue fired frame yields UNKNOWN_MESSAGE naming CueFired`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val fired = CueFired(
                msgId = "cf1",
                sentAtMs = 1L,
                cueId = "cue-001",
                eventId = "e1",
                firedAtServerMs = 1L,
                rehearsal = false,
            )
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), fired)))
            val reply = (incoming.receive() as Frame.Text).readText()
            val msg = WsJson.json.decodeFromString(WsMessage.serializer(), reply)
            assertTrue(msg is Error, "expected Error, got: $reply")
            val err = msg as Error
            assertEquals("UNKNOWN_MESSAGE", err.code)
            assertTrue(err.message.contains("CueFired"), "expected message to name CueFired, got: ${err.message}")
        }
    }

    @Test
    fun `binary frame is skipped and connection still serves ping`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            send(Frame.Binary(true, byteArrayOf(1, 2, 3)))
            val ping = ClockPing(msgId = "p-after-bin", sentAtMs = 2L, seq = 42L, clientTimeMs = 999L)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), ping)))
            val reply = (incoming.receive() as Frame.Text).readText()
            val msg = WsJson.json.decodeFromString(WsMessage.serializer(), reply)
            assertTrue(msg is ClockPong, "expected ClockPong after binary skip, got: $reply")
            val pong = msg as ClockPong
            assertEquals(42L, pong.seq)
            assertEquals(999L, pong.clientTimeMs)
        }
    }
}