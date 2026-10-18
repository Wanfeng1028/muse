package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.server.metrics.StageMetrics
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.server.testing.testApplication
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.io.TempDir
import java.io.File
import kotlin.test.Test

class RehearsalRouteDeepTest {

    @Test
    fun `rehearsal defaults to false`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(settings = settings)
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        val response = client.get("/api/rehearsal")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("\"rehearsal\""), "body should contain rehearsal key: $body")
        assertTrue(body.contains("false"), "body should contain false: $body")
    }

    @Test
    fun `rehearsal reflects hub change`(@TempDir tempDir: File) = testApplication {
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
        assertTrue(body.contains("\"rehearsal\""), "body should contain rehearsal key: $body")
        assertTrue(body.contains("true"), "body should contain true: $body")
    }

    @Test
    fun `rehearsal toggle back to false`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(settings = settings)
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        hub.setRehearsal(true)
        hub.setRehearsal(false)

        val response = client.get("/api/rehearsal")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("\"rehearsal\""), "body should contain rehearsal key: $body")
        assertTrue(body.contains("false"), "body should contain false: $body")
    }

    @Test
    fun `rehearsal response is json`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(settings = settings)
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        val response = client.get("/api/rehearsal")
        assertEquals(HttpStatusCode.OK, response.status)
        assertEquals(ContentType.Application.Json, response.contentType()?.withoutParameters())
    }

    @Test
    fun `rehearsal without settings store stays false`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        val metrics = StageMetrics()
        application { module(store, hub, settings, metrics) }

        hub.setRehearsal(true)

        val response = client.get("/api/rehearsal")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("\"rehearsal\""), "body should contain rehearsal key: $body")
        assertTrue(body.contains("false"), "body should contain false: $body")
    }

    @Test
    fun `rehearsal persists across hub instances`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub1 = SyncHub(settings = settings)
        val metrics = StageMetrics()

        hub1.setRehearsal(true)

        val hub2 = SyncHub(settings = settings)
        application { module(store, hub2, settings, metrics) }

        val response = client.get("/api/rehearsal")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("\"rehearsal\""), "body should contain rehearsal key: $body")
        assertTrue(body.contains("true"), "body should contain true: $body")
    }
}
