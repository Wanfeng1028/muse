package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.server.metrics.StageMetrics
import dev.stagecue.shared.oplog.FileOpLogStore
import dev.stagecue.shared.protocol.TriggerCue
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.nio.file.Files
import java.util.UUID

class OpLogRouteTest {

    @Test
    fun oplogEndpointReturnsAllEntries() = testApplication {
        val dataDir = Files.createTempDirectory("stagecue-oplog-route").toFile()
        val ds = Database.init(dataDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val opLog = FileOpLogStore(dataDir.resolve("oplog"))
        val hub = SyncHub(opLog = opLog)
        val metrics = StageMetrics()

        hub.handleTriggerCue(
            TriggerCue(
                msgId = UUID.randomUUID().toString(),
                sentAtMs = 1000L,
                cueId = "cue-a",
            )
        )
        hub.handleTriggerCue(
            TriggerCue(
                msgId = UUID.randomUUID().toString(),
                sentAtMs = 2000L,
                cueId = "cue-b",
            )
        )

        application {
            module(store, hub, settings, metrics)
        }

        val resp = client.get("/api/oplog")
        assertEquals(HttpStatusCode.OK, resp.status)
        val body = resp.bodyAsText()
        val first = body.indexOf("CUE_FIRED")
        assertTrue(first >= 0)
        val second = body.indexOf("CUE_FIRED", first + 1)
        assertTrue(second >= 0)
    }

    @Test
    fun oplogEndpointReturnsEmptyArrayOnFreshHub() = testApplication {
        val dataDir = Files.createTempDirectory("stagecue-oplog-empty").toFile()
        val ds = Database.init(dataDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val opLog = FileOpLogStore(dataDir.resolve("oplog"))
        val hub = SyncHub(opLog = opLog)
        val metrics = StageMetrics()

        application {
            module(store, hub, settings, metrics)
        }

        val resp = client.get("/api/oplog")
        assertEquals(HttpStatusCode.OK, resp.status)
        assertEquals("[]", resp.bodyAsText().trim())
    }
}
