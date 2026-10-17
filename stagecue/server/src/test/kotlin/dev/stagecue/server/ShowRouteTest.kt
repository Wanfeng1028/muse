package dev.stagecue.server

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.server.metrics.StageMetrics
import io.ktor.server.testing.testApplication
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode

class ShowRouteTest {

    @Test
    fun `show returns default show with all five cues`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        val response = client.get("/api/show")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("\"id\": \"show-default\""), "body should contain show id: $body")
        assertTrue(body.contains("\"cue-001\""), "missing cue-001 in $body")
        assertTrue(body.contains("\"cue-002\""), "missing cue-002 in $body")
        assertTrue(body.contains("\"cue-003\""), "missing cue-003 in $body")
        assertTrue(body.contains("\"cue-004\""), "missing cue-004 in $body")
        assertTrue(body.contains("\"cue-005\""), "missing cue-005 in $body")
    }

    @Test
    fun `two show requests increment show request counter to exactly two`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        val first = client.get("/api/show")
        assertEquals(HttpStatusCode.OK, first.status)
        val second = client.get("/api/show")
        assertEquals(HttpStatusCode.OK, second.status)

        val scraped = metrics.scrape()
        val line = scraped.lines().firstOrNull { it.startsWith("stagecue_http_show_requests_total") }
        assertNotNull(line, "counter line not present in scrape: $scraped")
        assertTrue(
            line!!.trim() == "stagecue_http_show_requests_total 2.0",
            "unexpected counter line: $line"
        )
    }

    @Test
    fun `rehearsal defaults to false`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        val response = client.get("/api/rehearsal")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("\"rehearsal\": false"), "expected rehearsal false but got: $body")
    }

    @Test
    fun `rehearsal reflects hub rehearsal mode after being set to true`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(settings = settings)
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        hub.setRehearsal(true)
        val response = client.get("/api/rehearsal")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("\"rehearsal\": true"), "expected rehearsal true but got: $body")
    }

    @Test
    fun `show cues carry order fields in ascending sequence`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        val response = client.get("/api/show")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()

        for (i in 1..5) {
            val cueIdIndex = body.indexOf("\"cue-00$i\"")
            assertTrue(cueIdIndex >= 0, "cue-00$i missing in $body")
            val orderIndex = body.indexOf("\"order\": $i", cueIdIndex)
            assertTrue(
                orderIndex > cueIdIndex,
                "expected order $i after cue-00$i in $body"
            )
        }
    }
}