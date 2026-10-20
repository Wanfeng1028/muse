package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ValidatorAssignedGlobalTest {

    private fun issuesOf(code: String): List<Issue> {
        val story = Parser(code).parse()
        return Validator.validate(story)
    }

    @Test
    fun setAfterUseInSameSceneNoUninit() {
        val code = """
            scene start:
              text: "{k}"
              set k = 1
              end
        """.trimIndent()

        val issues = issuesOf(code)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertTrue(uninit.isEmpty(), "assigned 是全局收集的，set 在 text 之后也不应报 UNINIT_VAR")

        val story = Parser(code).parse()
        val textLine = story.scenes[0].statements.filterIsInstance<com.interlude.dsl.Text>().first().line
        assertEquals(2, textLine, "text 语句应在第 2 行")
        val setLine = story.scenes[0].statements.filterIsInstance<com.interlude.dsl.SetVar>().first().line
        assertEquals(3, setLine, "set 语句应在第 3 行")
    }

    @Test
    fun setOnlyInUnreachableSceneNoUninit() {
        val code = """
            scene start:
              text: "{hp}"
              end
            scene dead:
              set hp = 100
              end
        """.trimIndent()

        val issues = issuesOf(code)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertTrue(uninit.isEmpty(), "hp 在不可达场景 dead 中被 set，全局收集后不应报 UNINIT_VAR")

        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(1, unreachable.size, "应恰好有 1 条 UNREACHABLE")
        assertEquals("dead", unreachable[0].sceneId, "UNREACHABLE 应指向场景 dead")
        assertEquals(Severity.WARNING, unreachable[0].severity, "UNREACHABLE 严重级别应为 WARNING")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "hp 在 start 的文本中被引用，不应报 UNUSED_VAR")
    }

    @Test
    fun useBeforeAnySetAcrossScenes() {
        val code = """
            scene start:
              jump -> b
            scene b:
              text: "{late}"
              end
            scene c:
              set late = 1
              end
        """.trimIndent()

        val issues = issuesOf(code)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertTrue(uninit.isEmpty(), "late 在场景 c 被 set，全局收集后不应报 UNINIT_VAR")

        val unreachable = issues.filter { it.code == "UNREACHABLE" }
        assertEquals(1, unreachable.size, "应恰好有 1 条 UNREACHABLE")
        assertEquals("c", unreachable[0].sceneId, "UNREACHABLE 应指向场景 c")
        assertEquals(Severity.WARNING, unreachable[0].severity, "UNREACHABLE 严重级别应为 WARNING")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "late 在场景 b 的文本中被引用，不应报 UNUSED_VAR")

        val undefinedTarget = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertFalse(undefinedTarget.isNotEmpty(), "jump -> b 的目标 b 存在，不应报 UNDEFINED_TARGET")
    }
}