package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorUnusedVarJumpUnreadTest {

    @Test
    fun setThenJumpUnreadWarns() {
        val source = """
            scene start:
              text: "开始"
              set x = 1
              jump -> b
            scene b:
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "应恰好报告一条 UNUSED_VAR")

        val issue = unused.single()
        assertEquals(Severity.WARNING, issue.severity, "UNUSED_VAR 的严重级别应为 WARNING")
        assertEquals("start", issue.sceneId, "未使用变量位于 start 场景")
        assertEquals(3, issue.line, "set x 应位于第 3 行")
        assertTrue(issue.message.contains("x"), "消息应包含变量名 x，实际为 ${issue.message}")
    }

    @Test
    fun setThenEndUnreadWarns() {
        val source = """
            scene start:
              set y = 5
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "应恰好报告一条 UNUSED_VAR")

        val issue = unused.single()
        assertEquals(Severity.WARNING, issue.severity, "UNUSED_VAR 的严重级别应为 WARNING")
        assertEquals("start", issue.sceneId, "未使用变量位于 start 场景")
        assertEquals(2, issue.line, "set y 应位于第 2 行")
        assertTrue(issue.message.contains("y"), "消息应包含变量名 y，实际为 ${issue.message}")
    }

    @Test
    fun readInJumpTargetSceneNoWarning() {
        val source = """
            scene start:
              set x = 1
              jump -> b
            scene b:
              text: "值 {x}"
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "跨场景引用也算使用，不应报告 UNUSED_VAR，实际为 $unused")
    }
}