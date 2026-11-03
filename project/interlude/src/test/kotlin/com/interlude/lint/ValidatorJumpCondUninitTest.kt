package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorJumpCondUninitTest {

    @Test
    fun jumpCondUnsetVarError() {
        val source = """
            scene start:
              jump -> a if hp > 0
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(1, uninit.size, "应恰好报告 1 条 UNINIT_VAR")
        val issue = uninit[0]
        assertEquals(Severity.ERROR, issue.severity, "严重级别应为 ERROR")
        assertEquals(2, issue.line, "行号应为第 2 行")
        assertEquals("start", issue.sceneId, "场景应为 start")
        assertTrue(issue.message.contains("hp"), "message 应包含变量名 hp")
        assertTrue(issue.message.contains("jump"), "message 应标明来自 jump 条件")
    }

    @Test
    fun jumpCondSetVarNoError() {
        val source = """
            scene start:
              set hp = 10
              jump -> a if hp > 0
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(0, uninit.size, "已 set 的变量不应报 UNINIT_VAR")
        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(0, unused.size, "hp 被条件引用，不应报 UNUSED_VAR")
    }

    @Test
    fun condExprMultiVarsPartialUnset() {
        val source = """
            scene start:
              set m = 1
              jump -> a if m + n > 0
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(1, uninit.size, "应恰好报告 1 条 UNINIT_VAR")
        assertEquals(Severity.ERROR, uninit[0].severity, "严重级别应为 ERROR")
        assertEquals(3, uninit[0].line, "行号应为第 3 行")
        assertTrue(uninit[0].message.contains("n"), "message 应包含未初始化变量 n")

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(0, unused.size, "m 被条件引用，n 从未 set，均不应报 UNUSED_VAR")
    }
}