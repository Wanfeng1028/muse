package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.protocol.*
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.server.testing.testApplication
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class MonitorWsSnapshotDeepTest {

    @TempDir
    lateinit var tempDir: File

    // 事实来源：Routes.kt MONITOR 分支先发送 Welcome，再构造并发送 StateSnapshot，showId 取自 store.getShow().id，states 为 show.cues 的 id->state 映射
    @Test
    fun `monitor hello receives welcome then state snapshot with matching show`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }
        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val hello = Hello(msgId = "h1", sentAtMs = 1L, clientId = "mon-1", role = ClientRole.MONITOR, clientTimeMs = 1L)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello)))

            val welcome = WsJson.json.decodeFromString(WsMessage.serializer(), (incoming.receive() as Frame.Text).readText())
            assertTrue(welcome is Welcome, "first frame must be Welcome, got: $welcome")
            assertEquals("mon-1", (welcome as Welcome).clientId)

            val snap = WsJson.json.decodeFromString(WsMessage.serializer(), (incoming.receive() as Frame.Text).readText())
            assertTrue(snap is StateSnapshot, "second frame must be StateSnapshot, got: $snap")
            val snapshot = snap as StateSnapshot

            val show = store.getShow()
            assertEquals(show.id, snapshot.showId)
            val expected = show.cues.associate { it.id to it.state }
            assertEquals(expected, snapshot.states)
        }
    }

    // 事实来源：Routes.kt MONITOR 分支 serverTimeMs = System.currentTimeMillis()（> 0）；SqliteShowStoreTest 的 `default show has 5 cues` 保证 states 非空
    @Test
    fun `monitor snapshot has positive server time and non-empty states`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }
        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val hello = Hello(msgId = "h2", sentAtMs = 1L, clientId = "mon-2", role = ClientRole.MONITOR, clientTimeMs = 1L)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello)))

            incoming.receive()
            val snap = WsJson.json.decodeFromString(WsMessage.serializer(), (incoming.receive() as Frame.Text).readText())
            assertTrue(snap is StateSnapshot)
            val snapshot = snap as StateSnapshot
            assertTrue(snapshot.serverTimeMs > 0L, "serverTimeMs should be positive, was ${snapshot.serverTimeMs}")
            assertTrue(snapshot.states.isNotEmpty(), "states should be non-empty")
            assertEquals(5, snapshot.states.size, "default show has 5 cues")
        }
    }

    // 事实来源：Routes.kt 中快照仅在 msg.role == ClientRole.MONITOR 时发送；DIRECTOR 且 lastSeenSeq 为 null 时 missedOps 为空故无后续帧
    @Test
    fun `director hello receives welcome and no state snapshot`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }
        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val hello = Hello(msgId = "h3", sentAtMs = 1L, clientId = "dir-1", role = ClientRole.DIRECTOR, clientTimeMs = 1L, lastSeenSeq = null)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello)))

            val welcome = WsJson.json.decodeFromString(WsMessage.serializer(), (incoming.receive() as Frame.Text).readText())
            assertTrue(welcome is Welcome, "first frame must be Welcome, got: $welcome")
            assertEquals("dir-1", (welcome as Welcome).clientId)

            val second = withTimeoutOrNull(2000) { incoming.receive() }
            assertTrue(second == null || second !is Frame.Text || run {
                val decoded = WsJson.json.decodeFromString(WsMessage.serializer(), second.readText())
                decoded !is StateSnapshot
            }, "DIRECTOR must not receive StateSnapshot, got: $second")
        }
    }

    // 事实来源：Routes.kt MONITOR 分支对每次 Hello 都发送全量快照，同一 clientId 重连（lastSeenSeq=null）仍收到 StateSnapshot
    @Test
    fun `monitor reconnect with same client id receives state snapshot again`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }
        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val hello1 = Hello(msgId = "h4a", sentAtMs = 1L, clientId = "mon-4", role = ClientRole.MONITOR, clientTimeMs = 1L)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello1)))
            incoming.receive()
            val snap1 = WsJson.json.decodeFromString(WsMessage.serializer(), (incoming.receive() as Frame.Text).readText())
            assertTrue(snap1 is StateSnapshot, "first connect must yield StateSnapshot, got: $snap1")

            val hello2 = Hello(msgId = "h4b", sentAtMs = 2L, clientId = "mon-4", role = ClientRole.MONITOR, clientTimeMs = 2L, lastSeenSeq = null)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello2)))
            val welcome2 = WsJson.json.decodeFromString(WsMessage.serializer(), (incoming.receive() as Frame.Text).readText())
            assertTrue(welcome2 is Welcome, "reconnect first frame must be Welcome, got: $welcome2")
            val snap2 = WsJson.json.decodeFromString(WsMessage.serializer(), (incoming.receive() as Frame.Text).readText())
            assertTrue(snap2 is StateSnapshot, "reconnect must yield StateSnapshot, got: $snap2")
            assertEquals((snap1 as StateSnapshot).showId, (snap2 as StateSnapshot).showId)
        }
    }

    // 事实来源：Routes.kt MONITOR 分支 states = show.cues.associate { it.id to it.state }，反序列化后 value 应为 CueState 枚举且 key 集合等于 cue id 集合
    @Test
    fun `monitor snapshot states values are cue states and keys match cue ids`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }
        val client = createClient { install(WebSockets) }
        client.webSocket("/ws") {
            val hello = Hello(msgId = "h5", sentAtMs = 1L, clientId = "mon-5", role = ClientRole.MONITOR, clientTimeMs = 1L)
            send(Frame.Text(WsJson.json.encodeToString(WsMessage.serializer(), hello)))
            incoming.receive()
            val snap = WsJson.json.decodeFromString(WsMessage.serializer(), (incoming.receive() as Frame.Text).readText())
            assertTrue(snap is StateSnapshot)
            val snapshot = snap as StateSnapshot

            val show = store.getShow()
            assertEquals(show.cues.map { it.id }.toSet(), snapshot.states.keys)
            for ((_, value) in snapshot.states) {
                assertTrue(value is CueState, "each state value must be CueState, got: $value")
            }
        }
    }
}