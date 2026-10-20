package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarCaseTest {

    @Test
    fun caseMismatchBothDirections() {
        val source = """
            scene start:
              set HP = 100
              text: "{hp}"
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        val unused = issues.filter { it.code == "UNUSED_VAR" }

        assertEquals(1, uninit.size, "应恰好有 1 条 UNINIT_VAR，因为占位符 {hp} 与 set 的 HP 大小写不同")
        assertEquals(Severity.ERROR, uninit[0].severity, "UNINIT_VAR 严重级别应为 ERROR")
        assertTrue(uninit[0].message.contains("hp"), "UNINIT_VAR 消息应包含小写 hp")
        assertEquals("start", uninit[0].sceneId, "UNINIT_VAR 应报告在 start 场景")
        assertEquals(3, uninit[0].line, "UNINIT_VAR 应报告在文本行 3")

        assertEquals(1, unused.size, "应恰好有 1 条 UNUSED_VAR，因为 set 的 HP 未被任何地方以相同大小写引用")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertTrue(unused[0].message.contains("HP"), "UNUSED_VAR 消息应包含大写 HP")
        assertEquals("start", unused[0].sceneId, "UNUSED_VAR 应报告在 start 场景")
        assertEquals(2, unused[0].line, "UNUSED_VAR 应报告在首次 set 的行 2")

        assertFalse(issues.any { it.code == "DEAD_END" }, "场景以 end 结尾，不应有 DEAD_END")
    }

    @Test
    fun exactCaseMatchNoWarning() {
        val source = """
            scene start:
              set Hp = 1
              text: "{Hp}"
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        assertFalse(issues.any { it.code == "UNUSED_VAR" }, "占位符 {Hp} 与 set 的 Hp 大小写完全一致，不应有 UNUSED_VAR")
        assertFalse(issues.any { it.code == "UNINIT_VAR" }, "变量 Hp 已被 set，不应有 UNINIT_VAR")
    }

    @Test
    fun upperInConditionLowerInSet() {
        val source = """
            scene start:
              set flag = 1
              jump -> a if FLAG > 0
              end
            scene a:
              end
        """.trimIndent()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        val unused = issues.filter { it.code == "UNUSED_VAR" }

        assertEquals(1, uninit.size, "条件中 FLAG 从未被 set，应恰好有 1 条 UNINIT_VAR")
        assertEquals(Severity.ERROR, uninit[0].severity, "UNINIT_VAR 严重级别应为 ERROR")
        assertTrue(uninit[0].message.contains("FLAG"), "UNINIT_VAR 消息应包含大写 FLAG")
        assertEquals("start", uninit[0].sceneId, "UNINIT_VAR 应报告在 start 场景")
        assertEquals(3, uninit[0].line, "UNINIT_VAR 应报告在 jump 行 3")

        assertEquals(1, unused.size, "set 的小写 flag 未在任何地方以相同大小写引用，应恰好有 1 条 UNUSED_VAR")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 严重级别应为 WARNING")
        assertTrue(unused[0].message.contains("flag"), "UNUSED_VAR 消息应包含小写 flag")
        assertEquals("start", unused[0].sceneId, "UNUSED_VAR 应报告在 start 场景")
        assertEquals(2, unused[0].line, "UNUSED_VAR 应报告在首次 set 的行 2")
    }
}