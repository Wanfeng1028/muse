package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorChoiceCondUninitTest {

    @Test
    fun choiceCondUnsetVarError() {
        val src = """
            |scene start:
            |  choice "去" -> a if hp > 0
            |  jump -> b
            |scene a:
            |  end
            |scene b:
            |  end
        """.trimMargin()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(1, uninit.size, "应恰好有 1 条 UNINIT_VAR")
        val issue = uninit[0]
        assertEquals(Severity.ERROR, issue.severity, "UNINIT_VAR 严重级别应为 ERROR")
        assertEquals(2, issue.line, "UNINIT_VAR 应报在 choice 所在行 2")
        assertEquals("start", issue.sceneId, "UNINIT_VAR 场景应为 start")
        assertTrue(issue.message.contains("hp"), "UNINIT_VAR 消息应包含变量名 hp")
        assertTrue(issue.message.contains("choice"), "UNINIT_VAR 消息应指明 choice 条件")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(0, unused.size, "没有 set 语句时不应有 UNUSED_VAR")
    }

    @Test
    fun choiceCondSetVarNoError() {
        val src = """
            |scene start:
            |  set hp = 10
            |  choice "去" -> a if hp > 0
            |  jump -> b
            |scene a:
            |  end
            |scene b:
            |  end
        """.trimMargin()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(0, uninit.size, "hp 已 set，不应有 UNINIT_VAR")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(0, unused.size, "hp 在 choice 条件中被引用，不应有 UNUSED_VAR")
    }

    @Test
    fun choiceWithoutConditionNoCheck() {
        val src = """
            |scene start:
            |  set x = 1
            |  choice "去" -> a
            |  jump -> b
            |scene a:
            |  end
            |scene b:
            |  end
        """.trimMargin()
        val story = Parser(src).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(0, uninit.size, "无条件 choice 不应触发 UNINIT_VAR")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "x 未被任何地方引用，应恰好 1 条 UNUSED_VAR")
        val issue = unused[0]
        assertEquals(Severity.WARNING, issue.severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertTrue(issue.message.contains("x"), "UNUSED_VAR 消息应包含变量名 x")
        assertEquals(2, issue.line, "UNUSED_VAR 行号应为首次 set 的行 2")
    }
}