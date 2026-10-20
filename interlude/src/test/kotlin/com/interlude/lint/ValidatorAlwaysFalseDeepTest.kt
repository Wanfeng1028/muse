package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorAlwaysFalseDeepTest {

    private fun parse(src: String) = Parser(src).parse()

    private fun alwaysFalse(issues: List<Issue>) = issues.filter { it.code == "ALWAYS_FALSE" }

    @Test
    fun arithmeticFalse() {
        val src = """
            scene start:
              jump -> a if 2 * 3 == 7
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()
        val issues = Validator.validate(parse(src))
        val af = alwaysFalse(issues)
        assertEquals(1, af.size, "应恰好报告 1 条 ALWAYS_FALSE，实际 ${af.size}")
        val issue = af[0]
        assertEquals(Severity.WARNING, issue.severity, "ALWAYS_FALSE 应为 WARNING")
        assertEquals("start", issue.sceneId, "应报告在 start 场景")
        assertEquals(2, issue.line, "应报告在第 2 行")
        assertTrue(issue.message.contains("恒为 false"), "消息应包含恒为 false，实际 ${issue.message}")
    }

    @Test
    fun notFalse() {
        val src = """
            scene start:
              jump -> a if not (1 == 1)
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()
        val issues = Validator.validate(parse(src))
        val af = alwaysFalse(issues)
        assertEquals(1, af.size, "应恰好报告 1 条 ALWAYS_FALSE，实际 ${af.size}")
        val issue = af[0]
        assertEquals(Severity.WARNING, issue.severity, "ALWAYS_FALSE 应为 WARNING")
        assertEquals(2, issue.line, "应报告在第 2 行")
    }

    @Test
    fun divByZeroNotFalse() {
        val src = """
            scene start:
              jump -> a if 1 / 0 == 0
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()
        val issues = Validator.validate(parse(src))
        val af = alwaysFalse(issues)
        assertEquals(0, af.size, "除零求值为 null，不应报告 ALWAYS_FALSE，实际 ${af.size}")
    }

    @Test
    fun alwaysTrueNoRule() {
        val src = """
            scene start:
              jump -> a if 1 == 1
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()
        val issues = Validator.validate(parse(src))
        val af = alwaysFalse(issues)
        assertEquals(0, af.size, "恒真无对应规则，不应报告 ALWAYS_FALSE，实际 ${af.size}")
        assertTrue(issues.isEmpty(), "该剧本应无任何 issue，实际 ${issues.map { it.code }}")
    }
}