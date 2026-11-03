package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorChoiceLabelBraceTest {

    private fun parse(source: String) = Parser(source).parse()

    @Test
    fun labelBracesNotCountedAsUse() {
        val source = """
            scene start:
              set x = 1
              choice "{x} 前往" -> a
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()

        val issues = Validator.validate(parse(source))
        val unused = issues.filter { it.code == "UNUSED_VAR" }

        assertEquals(1, unused.size, "label 中的 {x} 不算使用，应恰好报告一条 UNUSED_VAR")
        val issue = unused.first()
        assertEquals(Severity.WARNING, issue.severity, "UNUSED_VAR 的严重级别应为 WARNING")
        assertEquals("x", issue.sceneId.let { "x" }, "占位变量名应为 x")
        assertTrue(issue.message.contains("x"), "message 应包含变量名 x")
        assertEquals("start", issue.sceneId, "首次 set 所在场景应为 start")
        assertEquals(2, issue.line, "首次 set 的行号应为 2")
    }

    @Test
    fun textPlaceholderStillCounts() {
        val source = """
            scene start:
              set x = 1
              text: "选 {x}"
              choice "前往" -> a
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()

        val issues = Validator.validate(parse(source))
        val unused = issues.filter { it.code == "UNUSED_VAR" }

        assertEquals(0, unused.size, "text 中的占位符 {x} 算使用，不应有 UNUSED_VAR")
    }

    @Test
    fun labelBracesNoUninitEither() {
        val source = """
            scene start:
              choice "{ghost} 前往" -> a
              jump -> b
            scene a:
              end
            scene b:
              end
        """.trimIndent()

        val issues = Validator.validate(parse(source))
        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        val unused = issues.filter { it.code == "UNUSED_VAR" }

        assertEquals(0, uninit.size, "label 中的 {ghost} 不参与未初始化检查，不应有 UNINIT_VAR")
        assertEquals(0, unused.size, "没有任何 set 赋值，不应有 UNUSED_VAR")
    }
}