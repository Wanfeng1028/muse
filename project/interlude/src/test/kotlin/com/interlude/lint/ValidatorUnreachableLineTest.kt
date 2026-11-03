package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ValidatorUnreachableLineTest {

    @Test
    fun unreachableReportedAtHeaderLine() {
        val source = """
            scene start:
              jump -> b
            scene b:
              end
            scene far:
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)
        val unreachable = issues.filter { it.code == "UNREACHABLE" }

        assertEquals(1, unreachable.size, "应恰好报告一条 UNREACHABLE")
        val issue = unreachable[0]
        assertEquals("far", issue.sceneId, "UNREACHABLE 应指向场景 far")
        assertEquals(5, issue.line, "UNREACHABLE 行号应为场景头行 5 而非语句行")
        assertEquals(Severity.WARNING, issue.severity, "UNREACHABLE 严重级别应为 WARNING")
        assertTrue(issue.message.contains("far"), "消息应包含场景名 far")
    }

    @Test
    fun reachableViaChoiceChainNoWarning() {
        val source = """
            scene start:
              choice "去" -> b
            scene b:
              choice "回" -> start
              jump -> c
            scene c:
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)
        val unreachable = issues.filter { it.code == "UNREACHABLE" }

        assertTrue(unreachable.isEmpty(), "所有场景经 choice/jump 链可达，不应有 UNREACHABLE")
    }

    @Test
    fun entryIsFirstSceneNotNamedStart() {
        val source = """
            scene hub:
              jump -> leaf
            scene leaf:
              end
            scene start:
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)
        val unreachable = issues.filter { it.code == "UNREACHABLE" }

        assertEquals(1, unreachable.size, "应恰好报告一条 UNREACHABLE")
        val issue = unreachable[0]
        assertEquals("start", issue.sceneId, "入口是首个场景 hub，故 start 不可达")
        assertEquals(5, issue.line, "start 场景头位于第 5 行")
        assertEquals(Severity.WARNING, issue.severity, "UNREACHABLE 严重级别应为 WARNING")
        assertFalse(issue.sceneId == "hub", "入口场景 hub 本身不应被标记为不可达")
    }
}