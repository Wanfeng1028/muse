package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarRhsReadTest {

    @Test
    fun rhsReadMakesSourceUsed() {
        val source = """
            scene start:
              set flag = 1
              set other = flag
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "只有 other 从未被引用，应恰好报告 1 条 UNUSED_VAR")

        val otherIssue = unused.first()
        assertEquals(Severity.WARNING, otherIssue.severity, "UNUSED_VAR 应为 WARNING")
        assertEquals("start", otherIssue.sceneId, "other 的 UNUSED_VAR 应归属 start 场景")
        assertEquals(3, otherIssue.line, "other 的首次 set 在第 3 行")
        assertTrue(otherIssue.message.contains("other"), "警告信息应包含变量名 other")

        assertFalse(
            unused.any { it.message.contains("flag") },
            "flag 出现在 other 的右值中，应被视为已使用，不应产生 UNUSED_VAR"
        )
    }

    @Test
    fun nestedBinaryRhs() {
        val source = """
            scene start:
              set x = 1
              set y = (x + 2) * 3
              text: "{y}"
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "x 被 y 的嵌套二元右值引用，y 被文本占位符引用，不应有 UNUSED_VAR")
        assertFalse(unused.any { it.message.contains("x") }, "x 在嵌套表达式中被引用，不应报 UNUSED_VAR")
        assertFalse(unused.any { it.message.contains("y") }, "y 被文本占位符 {y} 引用，不应报 UNUSED_VAR")
    }

    @Test
    fun stringConcatRhs() {
        val source = """
            scene start:
              set name = "hero"
              set title = name + "!"
              text: "{title}"
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "name 被字符串拼接右值引用，title 被占位符引用，不应有 UNUSED_VAR")
        assertFalse(unused.any { it.message.contains("name") }, "name 出现在 title 的拼接右值中，应视为已使用")
        assertFalse(unused.any { it.message.contains("title") }, "title 被文本占位符 {title} 引用，应视为已使用")
    }
}