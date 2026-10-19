package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarTest {

    private fun lint(src: String): List<Issue> = Validator.validate(Parser(src).parse())

    private fun unused(issues: List<Issue>): List<Issue> = issues.filter { it.code == "UNUSED_VAR"}

    @Test
    fun usedInTextPlaceholderNoWarning() {
        val issues = lint(
            """
            scene start:
              text: "开始"
              set hp = 100
              text: "血量 {hp}"
              end
            """.trimIndent()
        )
        assertEquals(0, unused(issues).size)
    }

    @Test
    fun usedInChoiceConditionNoWarning() {
        val issues = lint(
            """
            scene start:
              set flag = 1
              choice "去A" -> a if flag > 0
              choice "去B" -> b
              end

            scene a:
              text: "A"
              end

            scene b:
              text: "B"
              end
            """.trimIndent()
        )
        assertEquals(0, unused(issues).size)
    }

    @Test
    fun usedInJumpConditionNoWarning() {
        val issues = lint(
            """
            scene start:
              set flag = 1
              jump -> a if flag > 0
              end

            scene a:
              text: "A"
              end
            """.trimIndent()
        )
        assertEquals(0, unused(issues).size)
    }

    @Test
    fun usedInOtherSceneTextNoWarning() {
        val issues = lint(
            """
            scene start:
              set hp = 100
              jump -> a

            scene a:
              text: "血量 {hp}"
              end
            """.trimIndent()
        )
        assertEquals(0, unused(issues).size)
    }

    @Test
    fun usedInOtherSetRhsNoWarning() {
        val issues = lint(
            """
            scene start:
              set a = 1
              set b = a
              text: "{b}"
              end
            """.trimIndent()
        )
        assertEquals(0, unused(issues).size)
    }

    @Test
    fun unusedVarReportsSingleWarningAtFirstSet() {
        val issues = lint(
            """
            scene start:
              text: "开始"
              set unused_flag = 1
              set hp = 100
              text: "血量 {hp}"
              end
            """.trimIndent()
        )
        val u = unused(issues)
        assertEquals(1, u.size)
        assertEquals(Severity.WARNING, u[0].severity)
        assertEquals("start", u[0].sceneId)
        assertEquals(3, u[0].line)
        assertTrue(u[0].message.contains("unused_flag"))
    }

    @Test
    fun repeatedSetOfUnusedVarReportsOnlyOne() {
        val issues = lint(
            """
            scene start:
              set unused_flag = 1
              set unused_flag = 2
              set hp = 100
              text: "{hp}"
              end
            """.trimIndent()
        )
        assertEquals(1, unused(issues).size)
    }

    @Test
    fun selfReferencingSetIsUsed() {
        val issues = lint(
            """
            scene start:
              set x = 1
              set x = x + 1
              text: "{x}"
              end
            """.trimIndent()
        )
        assertEquals(0, unused(issues).size)
    }

    @Test
    fun uninitVarErrorAndUnusedVarWarningCoexist() {
        val issues = lint(
            """
            scene start:
              set a = b
              text: "hello"
              end
            """.trimIndent()
        )
        val uninit = issues.filter { it.code == "UNINIT_VAR" && it.severity == Severity.ERROR}
        val u = unused(issues)
        assertEquals(1, uninit.size)
        assertEquals(1, u.size)
        assertEquals("a", u[0].code.let { "a" })
        assertTrue(u[0].message.contains("a"))
    }
}
