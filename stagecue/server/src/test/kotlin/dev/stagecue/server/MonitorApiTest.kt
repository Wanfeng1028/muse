package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.model.Show
import dev.stagecue.shared.model.MonitorState
import kotlinx.serialization.json.Json
import dev.stagecue.shared.protocol.*
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class MonitorApiTest {
    @TempDir
    lateinit var tempDir: File

    private fun newStore(): SqliteShowStore {
        val ds = Database.init(tempDir)
        return SqliteShowStore(ds)
    }

    @Test
    fun `monitor endpoint returns snapshot structure`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }
        val before = System.currentTimeMillis()
        val response = client.get("/api/monitor")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        val after = System.currentTimeMillis()
        // 根因：服务端 ContentNegotiation 配了 prettyPrint = true，字符串 contains 断言依赖空格格式必挂；
        // 改为解析 JSON 后断言结构，不再依赖序列化格式。
        val snapshot = Json { ignoreUnknownKeys = true }.decodeFromString<MonitorState>(body)
        assertNull(snapshot.current)
        assertNotNull(snapshot.next)
        assertEquals("cue-001", snapshot.next?.id)
        assertNull(snapshot.remainingMs)
        assertFalse(snapshot.rehearsal)
        assertTrue(snapshot.serverTimeMs in before..after,
            "serverTimeMs=${snapshot.serverTimeMs} not in [$before, $after]")
    }

    @Test
    fun `monitorSnapshot returns current next and remaining`() {
        val hub = SyncHub(clock = { 100000L })
        val c1 = Cue(id = "c1", name = "one", type = CueType.AUDIO, durationMs = 60000, order = 1)
        val c2 = Cue(id = "c2", name = "two", type = CueType.AUDIO, durationMs = 0, order = 2)
        val show = Show(id = "s1", name = "t", cues = listOf(c1, c2), createdAtMs = 0, updatedAtMs = 0)
        hub.handleTriggerCue(TriggerCue(msgId = "e1", sentAtMs = 99999L, cueId = "c1"))
        val snap = hub.monitorSnapshot(show)
        assertEquals("c1", snap.current?.id)
        assertEquals("c2", snap.next?.id)
        assertEquals(60000L, snap.remainingMs)
        assertFalse(snap.rehearsal)
    }

    @Test
    fun `monitorSnapshot counts down and null when no duration`() {
        var now = 100000L
        val hub = SyncHub(clock = { now })
        val c1 = Cue(id = "c1", name = "one", type = CueType.AUDIO, durationMs = 60000, order = 1)
        val c2 = Cue(id = "c2", name = "two", type = CueType.AUDIO, durationMs = 0, order = 2)
        val show = Show(id = "s1", name = "t", cues = listOf(c1, c2), createdAtMs = 0, updatedAtMs = 0)
        hub.handleTriggerCue(TriggerCue(msgId = "e1", sentAtMs = 99999L, cueId = "c1"))
        now = 110000L
        assertEquals(50000L, hub.monitorSnapshot(show).remainingMs)
        hub.handleTriggerCue(TriggerCue(msgId = "e2", sentAtMs = 110001L, cueId = "c2"))
        assertNull(hub.monitorSnapshot(show).remainingMs)
    }

    @Test
    fun `authorizeWrite blocks monitor only`() {
        val hub = SyncHub()
        val t = TriggerCue(msgId = "t", sentAtMs = 1L, cueId = "c1")
        val a = ArmCue(msgId = "a", sentAtMs = 1L, cueId = "c1")
        val s = SetRehearsal(msgId = "s", sentAtMs = 1L, enabled = true)

        val d1 = hub.authorizeWrite(ClientRole.MONITOR, t)
        assertNotNull(d1)
        assertEquals("FORBIDDEN", d1!!.code)

        val d2 = hub.authorizeWrite(ClientRole.MONITOR, a)
        assertNotNull(d2)
        assertEquals("FORBIDDEN", d2!!.code)

        val d3 = hub.authorizeWrite(ClientRole.MONITOR, s)
        assertNotNull(d3)
        assertEquals("FORBIDDEN", d3!!.code)

        assertNull(hub.authorizeWrite(ClientRole.DIRECTOR, t))
        assertNull(hub.authorizeWrite(null, t))
        assertNull(hub.authorizeWrite(ClientRole.MONITOR, ClockPing(msgId = "p", sentAtMs = 1L, seq = 1L, clientTimeMs = 1L)))
    }

    @Test
    fun `ws monitor receives snapshot and is denied writes`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val hello = Hello(msgId = "h1", sentAtMs = 1L, clientId = "mon-1",
                role = ClientRole.MONITOR, clientTimeMs = 1L)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello)))

            val welcome = (incoming.receive() as Frame.Text).readText()
            assertTrue(welcome.contains("\"kind\":\"welcome\""), "expected welcome, got: $welcome")

            val snap = (incoming.receive() as Frame.Text).readText()
            assertTrue(snap.contains("\"kind\":\"state_snapshot\""), "expected snapshot, got: $snap")

            val trig = TriggerCue(msgId = "t1", sentAtMs = 2L, cueId = "cue-001")
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), trig)))
            val err = (incoming.receive() as Frame.Text).readText()
            assertTrue(err.contains("\"code\":\"FORBIDDEN\""), "expected FORBIDDEN, got: $err")
        }

        assertNull(hub.monitorSnapshot(store.getShow()).current)
    }

    @Test
    fun `ws director can trigger and snapshot reflects current`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val hello = Hello(msgId = "h1", sentAtMs = 1L, clientId = "dir-1",
                role = ClientRole.DIRECTOR, clientTimeMs = 1L)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello)))

            val welcome = (incoming.receive() as Frame.Text).readText()
            assertTrue(welcome.contains("\"kind\":\"welcome\""), "expected welcome, got: $welcome")

            val trig = TriggerCue(msgId = "t1", sentAtMs = 2L, cueId = "cue-001")
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), trig)))
            val fired = (incoming.receive() as Frame.Text).readText()
            assertTrue(fired.contains("\"kind\":\"cue_fired\""), "expected cue_fired, got: $fired")
        }

        assertEquals("cue-001", hub.monitorSnapshot(store.getShow()).current?.id)
    }
}
