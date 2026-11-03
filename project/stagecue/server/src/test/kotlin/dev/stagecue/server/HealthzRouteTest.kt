package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class HealthzRouteTest {

    @TempDir
    lateinit var tempDir: File

    @Test
    fun `healthz returns ok`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val response = client.get("/healthz")
        assertEquals(HttpStatusCode.OK, response.status)
        assertTrue(response.bodyAsText().contains("\"ok\""), "body should contain ok")
    }

    @Test
    fun `api show returns default show`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val response = client.get("/api/show")
        assertEquals(HttpStatusCode.OK, response.status)
        assertTrue(response.bodyAsText().contains("开场音乐"))
    }
}
