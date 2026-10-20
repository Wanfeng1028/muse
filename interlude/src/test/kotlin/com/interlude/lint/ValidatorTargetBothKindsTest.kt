package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorTargetBothKindsTest {

    @Test
    fun choiceAndJumpMissingTargetsTwoErrors() {
        val source = """
            scene start:
              choice "去" -> ghost1
              jump -> ghost2
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val undefined = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertEquals(2, undefined.size, "choice 与 jump 目标缺失应各报告一条，共 2 条")
        assertTrue(undefined.all { it.severity == Severity.ERROR }, "UNDEFINED_TARGET 严重级别应为 ERROR")

        val choiceIssue = undefined.first { it.line == 2 }
        assertEquals(2, choiceIssue.line, "choice 目标缺失应报告在第 2 行")
        assertTrue(choiceIssue.message.contains("ghost1"), "choice 报错信息应包含目标场景名 ghost1")
        assertTrue(choiceIssue.message.contains("choice"), "choice 报错信息应包含 choice 关键字")

        val jumpIssue = undefined.first { it.line == 3 }
        assertEquals(3, jumpIssue.line, "jump 目标缺失应报告在第 3 行")
        assertTrue(jumpIssue.message.contains("ghost2"), "jump 报错信息应包含目标场景名 ghost2")
        assertTrue(jumpIssue.message.contains("jump"), "jump 报错信息应包含 jump 关键字")
    }

    @Test
    fun validTargetsNoError() {
        val source = """
            scene start:
              choice "去" -> a
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val undefined = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertTrue(undefined.isEmpty(), "所有目标场景均存在时不应产生 UNDEFINED_TARGET")
    }

    @Test
    fun targetCaseSensitive() {
        val source = """
            scene start:
              jump -> B
              end
            scene b:
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val undefined = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertEquals(1, undefined.size, "目标名大小写不同应视为不存在，恰好报告 1 条")
        val issue = undefined.first()
        assertEquals(Severity.ERROR, issue.severity, "UNDEFINED_TARGET 严重级别应为 ERROR")
        assertEquals("start", issue.sceneId, "报错应归属于场景 start")
        assertEquals(2, issue.line, "jump 目标缺失应报告在第 2 行")
        assertTrue(issue.message.contains("B"), "报错信息应包含目标名 B")
        assertFalse(issue.message.contains("'b'"), "报错信息不应把小写 b 当作已存在目标")
    }
}