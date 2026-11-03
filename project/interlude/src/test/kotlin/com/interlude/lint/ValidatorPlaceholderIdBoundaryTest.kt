package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ValidatorPlaceholderIdBoundaryTest {

    private fun issuesOf(code: String, source: String): List<Issue> {
        val story = Parser(source).parse()
        return Validator.validate(story).filter { it.code == code }
    }

    @Test
    fun digitStartNotExtracted() {
        val source = """
            scene start:
              set x = 1
              text: "值 {1x}"
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val all = Validator.validate(story)

        val uninit = all.filter { it.code == "UNINIT_VAR" }
        assertTrue(uninit.isEmpty(), "数字开头的 {1x} 不是合法占位符，不应产生 UNINIT_VAR")

        val unused = all.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "变量 x 从未被使用，应恰好报告一条 UNUSED_VAR")
        assertTrue(unused[0].message.contains("x"), "UNUSED_VAR 的 message 应包含变量名 x")
        assertEquals("start", unused[0].sceneId, "UNUSED_VAR 的 sceneId 应为 start")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 应为 WARNING")
    }

    @Test
    fun underscoreStartExtracted() {
        val source = """
            scene start:
              set _x = 7
              text: "值 {_x}"
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val all = Validator.validate(story)

        val unused = all.filter { it.code == "UNUSED_VAR" }
        assertTrue(unused.isEmpty(), "下划线开头的 {_x} 是合法占位符，_x 被使用，不应有 UNUSED_VAR")

        val uninit = all.filter { it.code == "UNINIT_VAR" }
        assertTrue(uninit.isEmpty(), "{_x} 是合法占位符且 _x 已被 set，不应有 UNINIT_VAR")
    }

    @Test
    fun digitInMiddleExtracted() {
        val positiveSource = """
            scene start:
              set hp2 = 50
              text: "血量 {hp2}"
              end
        """.trimIndent()

        val positiveAll = Validator.validate(Parser(positiveSource).parse())
        val positiveUnused = positiveAll.filter { it.code == "UNUSED_VAR" }
        assertTrue(positiveUnused.isEmpty(), "hp2 中的数字在中间，{hp2} 合法被提取，不应有 UNUSED_VAR")

        val negativeSource = """
            scene start:
              set hp = 50
              text: "血量 {hp2}"
              end
        """.trimIndent()

        val negativeAll = Validator.validate(Parser(negativeSource).parse())

        val uninit = negativeAll.filter { it.code == "UNINIT_VAR" }
        assertEquals(1, uninit.size, "文本引用 hp2 但从未 set，应恰好一条 UNINIT_VAR")
        assertTrue(uninit[0].message.contains("hp2"), "UNINIT_VAR 的 message 应包含 hp2")
        assertEquals(Severity.ERROR, uninit[0].severity, "UNINIT_VAR 应为 ERROR")

        val unused = negativeAll.filter { it.code == "UNUSED_VAR" }
        assertEquals(1, unused.size, "hp 被 set 但从未使用，应恰好一条 UNUSED_VAR")
        assertTrue(unused[0].message.contains("'hp'"), "UNUSED_VAR 的 message 应包含 'hp'")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 应为 WARNING")
    }
}