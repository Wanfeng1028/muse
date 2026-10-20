package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarSelfRefDeepTest {

    private fun parse(source: String) = Parser(source).parse()

    private fun issuesOf(source: String): List<Issue> = Validator.validate(parse(source))

    @Test
    fun selfRefWithoutOtherUseNoWarning() {
        val src = """
            scene start:
              set x = 1
              set x = x + 1
              end
        """.trimIndent()
        val issues = issuesOf(src)
        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(
            unused.isEmpty(),
            "set x = x + 1 右值引用了 x，应视为已使用，不应产生 UNUSED_VAR，实际: $unused"
        )
        assertFalse(
            issues.any { it.code == "UNINIT_VAR" },
            "x 在首行已被 set，第二行右值引用不应触发 UNINIT_VAR，实际: $issues"
        )
    }

    @Test
    fun rhsRefToNeverSetVar() {
        val src = """
            scene start:
              set a = b
              text: "hello"
              end
        """.trimIndent()
        val issues = issuesOf(src)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(1, uninit.size, "应恰好有 1 条 UNINIT_VAR，实际: $uninit")
        val uninitIssue = uninit[0]
        assertEquals(Severity.ERROR, uninitIssue.severity, "UNINIT_VAR 应为 ERROR")
        assertTrue(
            uninitIssue.message.contains("b"),
            "UNINIT_VAR 消息应包含变量名 'b'，实际: ${uninitIssue.message}"
        )
        assertEquals(2, uninitIssue.line, "UNINIT_VAR 行号应为 2")
        assertEquals("start", uninitIssue.sceneId, "UNINIT_VAR 场景应为 start")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "应恰好有 1 条 UNUSED_VAR，实际: $unused")
        val unusedIssue = unused[0]
        assertEquals(Severity.WARNING, unusedIssue.severity, "UNUSED_VAR 应为 WARNING")
        assertTrue(
            unusedIssue.message.contains("a"),
            "UNUSED_VAR 消息应包含变量名 'a'，实际: ${unusedIssue.message}"
        )
        assertEquals(2, unusedIssue.line, "UNUSED_VAR 行号应为 2")

        assertEquals(
            "UNINIT_VAR",
            issues[0].code,
            "排序后第 0 条应为 UNINIT_VAR（ERROR 排在 WARNING 之前），实际: ${issues[0]}"
        )
        assertEquals(Severity.ERROR, issues[0].severity, "排序后首条 severity 应为 ERROR")
    }

    @Test
    fun chainedRhsUse() {
        val src = """
            scene start:
              set m = 1
              set n = m * 2
              set p = n + m
              text: "{p}"
              end
        """.trimIndent()
        val issues = issuesOf(src)
        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(
            unused.isEmpty(),
            "m 被 n 与 p 的右值引用、n 被 p 的右值引用、p 被文本占位符引用，均不应产生 UNUSED_VAR，实际: $unused"
        )
        assertFalse(
            issues.any { it.code == "UNINIT_VAR" },
            "所有变量均在引用前被 set，不应产生 UNINIT_VAR，实际: $issues"
        )
    }
}
