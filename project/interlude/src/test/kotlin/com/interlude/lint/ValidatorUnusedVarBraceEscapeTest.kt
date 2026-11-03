package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorUnusedVarBraceEscapeTest {

    private fun validate(source: String): List<Issue> =
        Validator.validate(Parser(source).parse())

    private fun unusedVars(issues: List<Issue>): List<Issue> =
        issues.filter { it.code == "UNUSED_VAR" }

    @Test
    fun doubleBracesNotExtracted() {
        val source = """
            scene start:
              set hp = 100
              text: "{{hp}}"
              end
        """.trimIndent()

        val issues = validate(source)
        val unused = unusedVars(issues)

        assertEquals(1, unused.size, "双大括号解析出的名字 '{hp' 非法，不应被提取，hp 应被判定为未使用")
        val issue = unused[0]
        assertEquals(Severity.WARNING, issue.severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertEquals("UNUSED_VAR", issue.code, "问题代码应为 UNUSED_VAR")
        assertEquals("start", issue.sceneId, "未使用变量应报告在 set 所在场景 start")
        assertTrue(issue.message.contains("hp"), "提示信息应包含变量名 hp")
    }

    @Test
    fun singleBackslashEscapeConsumedByParser() {
        val source = """
            scene start:
              set hp = 100
              text: "\{hp}"
              end
        """.trimIndent()

        val issues = validate(source)
        val unused = unusedVars(issues)

        assertTrue(
            unused.isEmpty(),
            "单个反斜杠在解析期被消费，Text.value 变为 {hp} 并被提取，不应产生 UNUSED_VAR"
        )
    }

    @Test
    fun doubleBackslashKeepsBackslashInValue() {
        val source = """
            scene start:
              set hp = 100
              text: "\\{hp}"
              end
        """.trimIndent()

        val issues = validate(source)
        val unused = unusedVars(issues)

        assertEquals(1, unused.size, "解析后值为 \\{hp}，提取器遇到反斜杠跳过，hp 应被判定为未使用")
        val issue = unused[0]
        assertEquals(Severity.WARNING, issue.severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertEquals("UNUSED_VAR", issue.code, "问题代码应为 UNUSED_VAR")
        assertEquals("start", issue.sceneId, "未使用变量应报告在 set 所在场景 start")
        assertTrue(issue.message.contains("hp"), "提示信息应包含变量名 hp")
    }
}