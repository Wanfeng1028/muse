package dev.stagecue.server

import dev.stagecue.server.metrics.StageMetrics
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class StageMetricsTest {

    @Test
    fun wsConnectedIncrementsCounter() {
        val m = StageMetrics()
        m.wsConnected()
        val out = m.scrape()
        assertTrue(out.contains("stagecue_ws_connections_total 1.0"), "scrape: $out")
    }

    @Test
    fun cueTriggeredRehearsalTrue() {
        val m = StageMetrics()
        m.cueTriggered(true)
        val out = m.scrape()
        assertTrue(out.contains("rehearsal=\"true\""), "scrape: $out")
        assertTrue(out.contains("stagecue_cues_triggered_total{rehearsal=\"true\"} 1.0"), "scrape: $out")
    }

    @Test
    fun cueTriggeredRehearsalFalse() {
        val m = StageMetrics()
        m.cueTriggered(false)
        val out = m.scrape()
        assertTrue(out.contains("stagecue_cues_triggered_total{rehearsal=\"false\"} 1.0"), "scrape: $out")
    }

    @Test
    fun dbMigrationsAppliedGauge() {
        val m = StageMetrics()
        m.dbMigrationsApplied(2)
        val out = m.scrape()
        assertTrue(out.contains("stagecue_db_migrations_applied 2.0"), "scrape: $out")
    }
}
