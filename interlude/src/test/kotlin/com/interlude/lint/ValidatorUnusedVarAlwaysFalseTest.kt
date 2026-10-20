package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarAlwaysFalseTest {

    private fun issuesOf(source: String): List<Issue> = Validator.validate(Parser(source).parse())

    @Test
    fun unusedVarBesideAlwaysFalse() {
        val source = """
            scene start:
              set x = 1
              choice "去" -> a if 1 > 2
              choice "走" -> b
              end
            scene a:
              end
            scene b:
              end
        """.trimIndent()

        val issues = issuesOf(source)

        val alwaysFalse = issues.filter { it.code == "ALWAYS_FALSE" }
        assertEquals(1, alwaysFalse.size, "应恰好有 1 条 ALWAYS_FALSE")
        assertEquals(Severity.WARNING, alwaysFalse[0].severity, "ALWAYS_FALSE 应为 WARNING")
        assertEquals("start", alwaysFalse[0].sceneId, "ALWAYS_FALSE 应位于 start 场景")
        assertEquals(3, alwaysFalse[0].line, "ALWAYS_FALSE 行号应为 3")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "应恰好有 1 条 UNUSED_VAR")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 应为 WARNING")
        assertTrue(unused[0].message.contains("x"), "UNUSED_VAR 消息应包含变量名 x")
        assertEquals(2, unused[0].line, "UNUSED_VAR 行号应为首次 set 的行 2")
    }

    @Test
    fun varUsedOnlyInAlwaysFalseConditionCountsAsUse() {
        val source = """
            scene start:
              set flag = 1
              choice "去" -> a if flag > 100
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()

        val issues = issuesOf(source)

        assertFalse(
            issues.any { it.code == "UNUSED_VAR" },
            "flag 在条件中被引用即算使用，不应有 UNUSED_VAR"
        )
        assertFalse(
            issues.any { it.code == "ALWAYS_FALSE" },
            "flag > 100 含 VarRef，tryConstEval 返回 null，不应有 ALWAYS_FALSE"
        )
    }

    @Test
    fun literalFalseConditionNoVarNoUnusedVar() {
        val source = """
            scene start:
              jump -> a if 1 == 2
              end
            scene a:
              end
        """.trimIndent()

        val issues = issuesOf(source)

        assertEquals(1, issues.size, "应恰好有 1 条 issue")
        val issue = issues[0]
        assertEquals("ALWAYS_FALSE", issue.code, "唯一 issue 应为 ALWAYS_FALSE")
        assertEquals(Severity.WARNING, issue.severity, "ALWAYS_FALSE 应为 WARNING")
        assertEquals("start", issue.sceneId, "ALWAYS_FALSE 应位于 start 场景")
        assertEquals(2, issue.line, "ALWAYS_FALSE 行号应为 2")
        assertFalse(
            issues.any { it.code == "UNUSED_VAR" },
            "脚本中没有任何 set 赋值，不应有 UNUSED_VAR"
        )
    }
}