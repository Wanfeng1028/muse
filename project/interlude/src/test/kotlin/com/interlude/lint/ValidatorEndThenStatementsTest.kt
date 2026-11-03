package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorEndThenStatementsTest {

    @Test
    fun endThenTextNoDeadEnd() {
        val source = """
            scene start:
              end
              text: "尾声"
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertTrue(deadEnds.isEmpty(), "end 已存在，即便后面还有 text 语句也不应报告 DEAD_END，实际: $deadEnds")
    }

    @Test
    fun endThenJumpNoDeadEnd() {
        val source = """
            scene start:
              end
              jump -> b
            scene b:
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertTrue(deadEnds.isEmpty(), "end 已满足且存在 jump 出口，不应报告 DEAD_END，实际: $deadEnds")

        val undefinedTargets = issues.filter { it.code == "UNDEFINED_TARGET" }
        assertTrue(undefinedTargets.isEmpty(), "jump 目标 b 已定义，不应报告 UNDEFINED_TARGET，实际: $undefinedTargets")
    }

    @Test
    fun noEndNoExitDeadEnd() {
        val source = """
            scene start:
              text: "卡住"
              set x = 1
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val deadEnds = issues.filter { it.code == "DEAD_END" }
        assertEquals(1, deadEnds.size, "无出口且无 end 应恰好报告 1 条 DEAD_END，实际: $deadEnds")
        val deadEnd = deadEnds.first()
        assertEquals(Severity.WARNING, deadEnd.severity, "DEAD_END 严重级别应为 WARNING")
        assertEquals("start", deadEnd.sceneId, "DEAD_END 应指向场景 start")
        assertEquals(1, deadEnd.line, "DEAD_END 行号应为场景声明行 1")

        val unusedVars = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unusedVars.size, "变量 x 被 set 后从未使用，应恰好报告 1 条 UNUSED_VAR，实际: $unusedVars")
        val unused = unusedVars.first()
        assertEquals(Severity.WARNING, unused.severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertTrue(unused.message.contains("x"), "UNUSED_VAR 信息应包含变量名 x，实际: ${unused.message}")
        assertEquals(3, unused.line, "UNUSED_VAR 行号应为首次 set 的行 3")
    }
}