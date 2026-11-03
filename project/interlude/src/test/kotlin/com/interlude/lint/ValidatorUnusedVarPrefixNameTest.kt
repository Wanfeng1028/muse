package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarPrefixNameTest {

    private fun parse(source: String) = Parser(source).parse()

    private fun unusedVars(source: String): List<Issue> {
        val issues = Validator.validate(parse(source))
        return issues.filter { it.code == "UNUSED_VAR" }
    }

    @Test
    fun prefixNameNotConfused() {
        val source = """
            scene start:
              set ab = 1
              set a = 2
              text: "{a}"
              end
        """.trimIndent()

        val unused = unusedVars(source)

        assertEquals(1, unused.size, "应恰好报告 1 条 UNUSED_VAR，前缀名 ab 不应与 a 混淆")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 应为 WARNING 级别")
        assertEquals("start", unused[0].sceneId, "问题场景应为 start")
        assertEquals(2, unused[0].line, "首次 set ab 的行号应为 2")
        assertTrue(unused[0].message.contains("'ab'"), "message 应包含单引号包裹的变量名 'ab'")
        assertFalse(
            unused.any { it.message.contains("'a'") },
            "不应把变量 a 误报为未使用（a 被 text 占位符使用）"
        )
    }

    @Test
    fun longerNameUsedShorterUnused() {
        val source = """
            scene start:
              set score = 10
              set score2 = 20
              text: "{score2}"
              end
        """.trimIndent()

        val unused = unusedVars(source)

        assertEquals(1, unused.size, "应恰好报告 1 条 UNUSED_VAR，score2 被使用而 score 未使用")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 应为 WARNING 级别")
        assertEquals(2, unused[0].line, "score 首次 set 的行号应为 2")
        assertTrue(unused[0].message.contains("'score'"), "message 应包含未使用的变量名 'score'")
        assertFalse(
            unused.any { it.message.contains("'score2'") },
            "score2 已被占位符引用，不应报未使用"
        )
    }

    @Test
    fun underscoreSuffixDistinct() {
        val source = """
            scene start:
              set hp = 1
              set hp_max = 100
              text: "{hp_max}"
              end
        """.trimIndent()

        val unused = unusedVars(source)

        assertEquals(1, unused.size, "应恰好报告 1 条 UNUSED_VAR，下划线后缀名 hp_max 与 hp 应视为不同变量")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 应为 WARNING 级别")
        assertEquals("start", unused[0].sceneId, "问题场景应为 start")
        assertEquals(2, unused[0].line, "hp 首次 set 的行号应为 2")
        assertTrue(unused[0].message.contains("'hp'"), "message 应包含未使用的变量名 'hp'")
        assertFalse(
            unused.any { it.message.contains("'hp_max'") },
            "hp_max 已被占位符引用，不应报未使用"
        )
    }
}