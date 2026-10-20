package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorUninitAndUnusedPairTest {

    @Test
    fun setFromUnsetVarBothFire() {
        val source = """
            scene start:
              set a = b
              text: "hello"
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        val unused = issues.filter { it.code == "UNUSED_VAR" }

        assertEquals(1, uninit.size, "应恰好有 1 条 UNINIT_VAR")
        val u = uninit[0]
        assertEquals(Severity.ERROR, u.severity, "UNINIT_VAR 严重级别应为 ERROR")
        assertEquals(2, u.line, "UNINIT_VAR 应报在第 2 行")
        assertEquals("start", u.sceneId, "UNINIT_VAR 场景应为 start")
        assertTrue(u.message.contains("b"), "UNINIT_VAR 消息应包含未初始化变量 b")

        assertEquals(1, unused.size, "应恰好有 1 条 UNUSED_VAR")
        val v = unused[0]
        assertEquals(Severity.WARNING, v.severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertEquals(2, v.line, "UNUSED_VAR 应报在第 2 行（首次 set 处）")
        assertEquals("start", v.sceneId, "UNUSED_VAR 场景应为 start")
        assertTrue(v.message.contains("a"), "UNUSED_VAR 消息应包含未使用变量 a")

        val idxError = issues.indexOfFirst { it.severity == Severity.ERROR }
        val idxWarning = issues.indexOfFirst { it.severity == Severity.WARNING }
        assertTrue(idxError >= 0 && idxWarning >= 0, "应同时存在 ERROR 与 WARNING 条目")
        assertTrue(idxError < idxWarning, "排序后 ERROR 应排在 WARNING 之前")
    }

    @Test
    fun unsetVarLaterSetFixesUninitButNotUnused() {
        val source = """
            scene start:
              text: "{k}"
              set k = 1
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        val unused = issues.filter { it.code == "UNUSED_VAR" }

        assertEquals(0, uninit.size, "assigned 是全局收集，set 在文本之后仍应消除 UNINIT_VAR")
        assertEquals(0, unused.size, "k 在文本占位符中被引用，不应报 UNUSED_VAR")
    }

    @Test
    fun twoUnsetOneUnused() {
        val source = """
            scene start:
              set a = b + c
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        val unused = issues.filter { it.code == "UNUSED_VAR" }

        assertEquals(2, uninit.size, "应恰好有 2 条 UNINIT_VAR（b 与 c）")
        assertTrue(uninit.all { it.severity == Severity.ERROR }, "所有 UNINIT_VAR 都应为 ERROR")
        assertTrue(uninit.all { it.line == 2 }, "两条 UNINIT_VAR 都应报在第 2 行")
        assertTrue(uninit.all { it.sceneId == "start" }, "两条 UNINIT_VAR 场景均应为 start")
        assertTrue(uninit.any { it.message.contains("b") }, "应有一条 UNINIT_VAR 消息含 b")
        assertTrue(uninit.any { it.message.contains("c") }, "应有一条 UNINIT_VAR 消息含 c")

        assertEquals(1, unused.size, "应恰好有 1 条 UNUSED_VAR（a）")
        val v = unused[0]
        assertEquals(Severity.WARNING, v.severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertEquals(2, v.line, "UNUSED_VAR 应报在第 2 行")
        assertTrue(v.message.contains("a"), "UNUSED_VAR 消息应包含未使用变量 a")

        assertEquals(3, issues.size, "总计应为 3 条 issue")
    }
}