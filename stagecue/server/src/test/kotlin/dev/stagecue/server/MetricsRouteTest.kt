package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.server.metrics.StageMetrics
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.nio.file.Files

class MetricsRouteTest {

    @Test
    fun metricsEndpointReturnsPrometheusText() = testApplication {
        val dataDir = Files.createTempDirectory("stagecue-metrics").toFile()
        val ds = Database.init(dataDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        val metrics = StageMetrics()

        application {
            module(store, hub, settings, metrics)
        }

        val resp = client.get("/metrics")
        assertEquals(HttpStatusCode.OK, resp.status)
        assertTrue(resp.headers["Content-Type"]?.contains("text/plain") == true)
        assertTrue(resp.bodyAsText().contains("stagecue_ws_connections_total"))
    }

    @Test
    fun showRequestIncrementsCounter() = testApplication {
        val dataDir = Files.createTempDirectory("stagecue-metrics2").toFile()
        val ds = Database.init(dataDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        val metrics = StageMetrics()

        application {
            module(store, hub, settings, metrics)
        }

        client.get("/api/show")
        val resp = client.get("/metrics")
        assertTrue(resp.bodyAsText().contains("stagecue_http_show_requests_total 1.0"))
    }
}
