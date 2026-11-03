package dev.stagecue.server

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlin.test.fail

class AlertRulesTest {

    private val whitelist = setOf(
        "stagecue_ws_connections",
        "stagecue_ws_disconnections",
        "stagecue_cues_triggered",
        "stagecue_cues_armed",
        "stagecue_http_show_requests",
        "stagecue_http_rate_limited_total",
        "stagecue_ws_broadcast_dropped_total",
        "stagecue_db_migrations_applied",
    )

    private val alertNames = listOf(
        "StageCueDown",
        "StageCueWsDisconnectSpike",
        "StageCueRateLimitSpike",
        "StageCueBroadcastDrop",
        "StageCueDbMigrationStuck",
    )

    private fun readRules(): String {
        val stream = javaClass.getResourceAsStream("/alerts/stagecue.rules.yml")
            ?: fail("规则文件未打包进 classpath")
        assertNotNull(stream)
        return stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
    }

    @Test
    fun test_规则文件结构完整() {
        val text = readRules()
        assertTrue(text.contains("groups:"), "缺少顶层 groups 键")
        for (name in alertNames) {
            val count = Regex("alert:\\s*$name\\b").findAll(text).count()
            assertTrue(count == 1, "告警 $name 出现次数应为 1，实际 $count")
        }
    }

    @Test
    fun test_expr只引用白名单指标() {
        val text = readRules()
        val metricRegex = Regex("stagecue_[a-z_0-9]+")
        val used = metricRegex.findAll(text).map { it.value }.toSet()
        assertTrue(used.isNotEmpty(), "没有从规则里提取到任何 stagecue_ 指标，说明规则写歪了")
        val offenders = used.filterNot { it in whitelist }
        assertTrue(offenders.isEmpty(), "规则里引用了白名单之外的指标: $offenders")
    }

    @Test
    fun test_每条规则有for和severity() {
        val text = readRules()
        val forCount = Regex("(?m)^\\s*for:\\s*\\S+").findAll(text).count()
        assertTrue(forCount >= 5, "for: 至少出现 5 次，实际 $forCount")
        assertTrue(text.contains("severity: critical"), "缺少 severity: critical")
        assertTrue(text.contains("severity: warning"), "缺少 severity: warning")
    }

    @Test
    fun test_无tab缩进() {
        val text = readRules()
        text.lineSequence().forEachIndexed { idx, line ->
            assertFalse(line.contains('\t'), "第 ${idx + 1} 行含 tab，YAML 禁用 tab 缩进")
        }
    }
}
