package com.interlude.lint

import com.interlude.dsl.Parser
import com.interlude.dsl.Story
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorDeepTest {

    private fun issuesOf(dsl: String): List<Issue> =
        Validator.validate(Parser(dsl.trimIndent()).parse())

    @Test
    fun jumpUndefinedTargetReportsError() {
        val issues = issuesOf(
            """
            scene a:
              jump -> nowhere
            """.trimIndent()
        )
        val undefined = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertEquals(1, undefined.size)
        assertEquals(Severity.ERROR, undefined[0].severity)
        assertEquals("a", undefined[0].sceneId)
    }

    @Test
    fun choiceToExistingTargetNoUndefined() {
        val issues = issuesOf(
            """
            scene a:
              choice "go" -> b
            scene b:
              end
            """.trimIndent()
        )
        assertTrue(issues.none { it.code == "UNDEFINED_TARGET" })
    }

    @Test
    fun emptySceneReportsDeadEnd() {
        val dsl =
            """
            scene a:
              end
            scene lonely:
            """.trimIndent()
        val issues = issuesOf(dsl)
        val dead = issues.filter { it.code == "DEAD_END" }
        assertEquals(1, dead.size)
        assertEquals(Severity.WARNING, dead[0].severity)
        assertEquals("lonely", dead[0].sceneId)
        assertEquals(3, dead[0].line)
    }

    @Test
    fun sceneWithEndNoDeadEnd() {
        val issues = issuesOf(
            """
            scene a:
              end
            """.trimIndent()
        )
        assertTrue(issues.none { it.code == "DEAD_END" })
    }

    @Test
    fun sceneWithChoiceNoDeadEnd() {
        val issues = issuesOf(
            """
            scene a:
              choice "go" -> b
            scene b:
              end
            """.trimIndent()
        )
        assertTrue(issues.none { it.code == "DEAD_END" })
    }

    @Test
    fun selfLoopReachable() {
        val issues = issuesOf(
            """
            scene a:
              jump -> a
            """.trimIndent()
        )
        assertTrue(issues.none { it.code == "UNREACHABLE" })
    }

    @Test
    fun chainReachable() {
        val issues = issuesOf(
            """
            scene a:
              jump -> b
            scene b:
              jump -> c
            scene c:
              end
            """.trimIndent()
        )
        assertTrue(issues.none { it.code == "UNREACHABLE" })
    }

    @Test
    fun missingTargetChoiceDoesNotAffectBfs() {
        val issues = issuesOf(
            """
            scene a:
              choice "go" -> nowhere
            scene b:
              end
            """.trimIndent()
        )
        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(1, unreachable.size)
        assertEquals("b", unreachable[0].sceneId)
        assertTrue(unreachable.none { it.sceneId == "a" })
    }

    @Test
    fun setExprUndefinedVarReportsUninit() {
        val issues = issuesOf(
            """
            scene a:
              set y = x + 1
              end
            """.trimIndent()
        )
        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(1, uninit.size)
        assertEquals(Severity.ERROR, uninit[0].severity)
    }

    @Test
    fun jumpConditionUndefinedVarReportsUninit() {
        val issues = issuesOf(
            """
            scene a:
              jump -> b if score > 10
            scene b:
              end
            """.trimIndent()
        )
        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(1, uninit.size)
        assertEquals(Severity.ERROR, uninit[0].severity)
    }

    @Test
    fun placeholderGlobalAcrossScenes() {
        val issues = issuesOf(
            """
            scene a:
              text: "hi {name}"
              jump -> b
            scene b:
              set name = "x"
              end
            """.trimIndent()
        )
        assertTrue(issues.none { it.code == "UNINIT_VAR" })
    }

    @Test
    fun selfReferenceSetNoUninit() {
        val issues = issuesOf(
            """
            scene a:
              set x = x + 1
              end
            """.trimIndent()
        )
        assertTrue(issues.none { it.code == "UNINIT_VAR" })
    }

    @Test
    fun alwaysFalseMatrix() {
        val falseCases = listOf(
            """
            scene a:
              jump -> b if 1 == 2
            scene b:
              end
            """.trimIndent(),
            """
            scene a:
              jump -> b if not (1 == 1)
            scene b:
              end
            """.trimIndent()
        )
        for (dsl in falseCases) {
            val issues = Validator.validate(Parser(dsl).parse())
            assertTrue(
                issues.any { it.code == "ALWAYS_FALSE" },
                "expected ALWAYS_FALSE for: $dsl"
            )
        }

        val nonFalseCases = listOf(
            """
            scene a:
              jump -> b if 1 == 1
            scene b:
              end
            """.trimIndent(),
            """
            scene a:
              jump -> b if 0
            scene b:
              end
            """.trimIndent(),
            """
            scene a:
              jump -> b if false
            scene b:
              end
            """.trimIndent(),
            """
            scene a:
              jump -> b if 1 / 0 == 0
            scene b:
              end
            """.trimIndent()
        )
        for (dsl in nonFalseCases) {
            val issues = Validator.validate(Parser(dsl).parse())
            assertFalse(
                issues.any { it.code == "ALWAYS_FALSE" },
                "unexpected ALWAYS_FALSE for: $dsl"
            )
        }
    }

    @Test
    fun variableConditionNoAlwaysFalseNoUninit() {
        val issues = issuesOf(
            """
            scene a:
              set n = 1
              jump -> b if n > 2
            scene b:
              end
            """.trimIndent()
        )
        assertFalse(issues.any { it.code == "ALWAYS_FALSE" })
        assertFalse(issues.any { it.code == "UNINIT_VAR" })
    }

    @Test
    fun orderingErrorBeforeWarning() {
        val issues = issuesOf(
            """
            scene a:
              end
            scene b:
              end
            scene lonely:
            scene d:
              end
            scene e:
              end
            scene f:
              end
            scene g:
              end
            scene h:
              jump -> nowhere
            """.trimIndent()
        )
        assertTrue(issues.isNotEmpty())
        assertEquals(Severity.ERROR, issues[0].severity)
        assertEquals("UNDEFINED_TARGET", issues[0].code)
        val errorIndex = issues.indexOfFirst { it.severity == Severity.ERROR }
        val warningIndex = issues.indexOfFirst { it.severity == Severity.WARNING }
        assertTrue(warningIndex == -1 || errorIndex < warningIndex)
    }

    @Test
    fun emptyStoryReturnsEmptyList() {
        val issues = Validator.validate(Story(emptyList()))
        assertTrue(issues.isEmpty())
    }

    @Test
    fun formatTextEmptyList() {
        val text = Report.formatText(emptyList())
        assertEquals("issues: 0 (errors: 0, warnings: 0)", text)
    }

    @Test
    fun formatJsonEscapesSpecialChars() {
        val issue = Issue(Severity.ERROR, "X", "a\"b\nc", "s", 1)
        val json = Report.formatJson(listOf(issue))
        assertTrue(json.contains("a\\\"b"))
        assertTrue(json.contains("\\n"))
        assertTrue(json.contains("\"issues\":1"))
        assertTrue(json.contains("\"errors\":1"))
        assertTrue(json.contains("\"warnings\":0"))
    }

    @Test
    fun endToEndCounts() {
        val dsl =
            """
            scene a:
              jump -> nowhere
            scene lonely:
            scene unreach:
              end
            """.trimIndent()
        val issues = Validator.validate(Parser(dsl).parse())
        val text = Report.formatText(issues)
        val firstLine = text.lines().first()
        // a: UNDEFINED_TARGET(ERROR)；lonely: DEAD_END + UNREACHABLE(2 WARNING)；unreach: UNREACHABLE(1 WARNING)
        assertEquals("issues: 4 (errors: 1, warnings: 3)", firstLine)
    }
}
