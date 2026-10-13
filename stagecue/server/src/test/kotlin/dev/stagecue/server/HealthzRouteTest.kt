package dev.stagecue.server

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
        val store = ShowStore(tempDir)
        val hub = SyncHub()
        application {
            module(store, hub)
        }
        val response = client.get("/healthz")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("\"ok\""), "body should contain ok: $body")
    }

    @Test
    fun `api show returns default show`() = testApplication {
        val store = ShowStore(tempDir)
        val hub = SyncHub()
        application {
            module(store, hub)
        }
        val response = client.get("/api/show")
        assertEquals(HttpStatusCode.OK, response.status)
        val body = response.bodyAsText()
        assertTrue(body.contains("开场音乐"), "should include default cue: $body")
    }
}
