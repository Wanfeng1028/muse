package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ValidatorDeadEndTargetInteractionTest {

    @Test
    fun choiceToMissingTargetNoDeadEnd() {
        val source = """
            scene start:
              choice "去" -> nowhere
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertTrue(deadEnds.isEmpty(), "存在 choice 出口时不应报 DEAD_END，实际: $deadEnds")

        val undefinedTargets = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertEquals(1, undefinedTargets.size, "choice 指向不存在场景应恰好报告 1 条 UNDEFINED_TARGET")

        val issue = undefinedTargets.single()
        assertEquals(Severity.ERROR, issue.severity, "UNDEFINED_TARGET 严重级别应为 ERROR")
        assertEquals(2, issue.line, "UNDEFINED_TARGET 行号应指向 choice 语句所在行 2")
        assertTrue(issue.message.contains("nowhere"), "报错信息应包含缺失目标名 nowhere，实际: ${issue.message}")
    }

    @Test
    fun jumpToMissingTargetNoDeadEnd() {
        val source = """
            scene start:
              jump -> nowhere
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertTrue(deadEnds.isEmpty(), "存在 jump 出口时不应报 DEAD_END，实际: $deadEnds")

        val undefinedTargets = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertEquals(1, undefinedTargets.size, "jump 指向不存在场景应恰好报告 1 条 UNDEFINED_TARGET")

        val issue = undefinedTargets.single()
        assertEquals(Severity.ERROR, issue.severity, "UNDEFINED_TARGET 严重级别应为 ERROR")
        assertEquals(2, issue.line, "UNDEFINED_TARGET 行号应指向 jump 语句所在行 2")
        assertTrue(issue.message.contains("nowhere"), "报错信息应包含缺失目标名 nowhere，实际: ${issue.message}")
    }

    @Test
    fun trulyDeadSceneStillDeadEnd() {
        val source = """
            scene start:
              text: "困住了"
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertEquals(1, deadEnds.size, "无出口且未以 end 结尾的场景应恰好报告 1 条 DEAD_END")

        val issue = deadEnds.single()
        assertEquals(Severity.WARNING, issue.severity, "DEAD_END 严重级别应为 WARNING")
        assertEquals("start", issue.sceneId, "DEAD_END 场景 id 应为 start")
        assertEquals(1, issue.line, "DEAD_END 行号应为场景头所在行 1")

        val undefinedTargets = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertTrue(undefinedTargets.isEmpty(), "无 choice/jump 时不应报告 UNDEFINED_TARGET，实际: $undefinedTargets")
    }
}
