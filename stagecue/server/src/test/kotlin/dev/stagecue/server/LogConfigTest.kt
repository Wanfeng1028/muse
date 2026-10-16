package dev.stagecue.server

import ch.qos.logback.classic.LoggerContext
import ch.qos.logback.classic.joran.JoranConfigurator
import ch.qos.logback.core.status.Status
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * v0.4.0 可观测性收尾：logback 配置与日志目录解析的回归测试。
 */
class LogConfigTest {

    private fun readLogbackXml(): String {
        val stream = javaClass.getResourceAsStream("/logback.xml")
        assertNotNull(stream, "classpath 上必须存在 /logback.xml")
        return stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
    }

    @Test
    fun test_logback_xml_可被解析() {
        val xml = readLogbackXml()

        // 用真实的 JoranConfigurator 解析到独立 LoggerContext，避免污染全局 context
        val context = LoggerContext()
        try {
            val configurator = JoranConfigurator()
            configurator.context = context

            val tmp = File.createTempFile("logback-parse-test", ".xml")
            try {
                tmp.writeText(xml)
                configurator.doConfigure(tmp)
            } finally {
                tmp.delete()
            }

            val statusManager = context.statusManager
            val errors = statusManager.getCopyOfStatusList()
                .filter { it.level >= Status.ERROR }
            assertTrue(
                errors.isEmpty(),
                "logback.xml 解析出现 ERROR 及以上状态: " +
                    errors.joinToString("; ") { "${it.level}: ${it.message}" },
            )
        } finally {
            context.stop()
        }
    }

    @Test
    fun test_resolveLogDir_拼接正确() {
        val resolved = resolveLogDir(File("/var/lib/stagecue"))
        assertTrue(
            resolved.absolutePath.endsWith("logs"),
            "期望以 logs 结尾，实际: ${resolved.absolutePath}",
        )
        assertEquals(
            "/var/lib/stagecue",
            resolved.parentFile?.absolutePath,
            "logs 的父目录必须是 dataDir",
        )
    }

    @Test
    fun test_logback_xml_含滚动策略关键字() {
        val xml = readLogbackXml()
        assertTrue(xml.contains("TimeBasedRollingPolicy"), "缺少 TimeBasedRollingPolicy")
        assertTrue(xml.contains("SizeAndTimeBasedFNATP"), "缺少 SizeAndTimeBasedFNATP")
        assertTrue(xml.contains("maxHistory"), "缺少 maxHistory")
        assertTrue(xml.contains("totalSizeCap"), "缺少 totalSizeCap")
        assertTrue(xml.contains("stagecue.log.dir"), "缺少 stagecue.log.dir 占位符")
    }

    @Test
    fun test_环境变量默认值语法() {
        val xml = readLogbackXml()
        // 红线 2：不许用 <if>，只允许 ${name:-default}
        assertFalse(xml.contains("<if"), "不允许使用 <if> 条件语法（需 janino）")
        assertTrue(
            xml.contains("STAGECUE_LOG_LEVEL:-INFO"),
            "root level 必须使用 \${STAGECUE_LOG_LEVEL:-INFO} 默认值语法",
        )
    }
}
