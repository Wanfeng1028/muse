package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.server.testing.testApplication
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class ReadyzRouteDeepTest {
    @TempDir
    lateinit var tempDir: File

    private fun ApplicationTestBuilderLikeSetup() {}

    @Test
    fun `readyz ready returns 200 with ready body`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings, readiness = { true }) }
        val response = client.get("/readyz")
        // 事实来源：Routes.kt get("/readyz") 中 if (readiness()) 为真时 call.respondText("{\"status\":\"ready\"}")，默认 200
        assertEquals(HttpStatusCode.OK, response.status)
        assertEquals("{\"status\":\"ready\"}", response.bodyAsText())
    }

    @Test
    fun `readyz not ready returns 503 with not_ready body`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings, readiness = { false }) }
        val response = client.get("/readyz")
        // 事实来源：Routes.kt else 分支 text = "{\"status\":\"not_ready\"}" 且 status = HttpStatusCode.ServiceUnavailable
        assertEquals(HttpStatusCode.ServiceUnavailable, response.status)
        assertEquals("{\"status\":\"not_ready\"}", response.bodyAsText())
    }

    @Test
    fun `readyz not ready returns json content type`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings, readiness = { false }) }
        val response = client.get("/readyz")
        // 事实来源：Routes.kt else 分支显式传入 contentType = ContentType.Application.Json
        val ct = response.contentType()?.toString() ?: ""
        assertTrue(ct.contains("application/json"), "expected application/json but was $ct")
    }

    @Test
    fun `readyz default readiness returns 200`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }
        val response = client.get("/readyz")
        // 事实来源：Main.kt module 签名中 readiness: () -> Boolean = { true } 的默认值，进入 if (readiness()) 分支
        assertEquals(HttpStatusCode.OK, response.status)
        assertEquals("{\"status\":\"ready\"}", response.bodyAsText())
    }

    @Test
    fun `readyz readiness throws returns 500`() = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application {
            module(store, hub, settings, readiness = { throw RuntimeException("db down") })
        }
        val response = client.get("/readyz")
        // 事实来源：Routes.kt if (readiness()) 直接调用无 try/catch，异常向上传播由 ktor 默认异常处理返回 500
        assertEquals(HttpStatusCode.InternalServerError, response.status)
    }
}
