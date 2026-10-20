package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorUnusedVarReadDeepTest {

    private fun unusedVarIssues(src: String): List<Issue> {
        val story = Parser(src).parse()
        return Validator.validate(story).filter { it.code == "UNUSED_VAR" }
    }

    @Test
    fun condReadInChoiceNoWarning() {
        val src = """
            scene start:
              set flag = 1
              choice "去A" -> a if flag > 0
              choice "去B" -> b
              end
            scene a:
              end
            scene b:
              end
        """.trimIndent()

        val issues = unusedVarIssues(src)

        assertTrue(
            issues.isEmpty(),
            "flag 在 choice 条件中被引用应算作使用，不应报 UNUSED_VAR，实际: $issues"
        )
        assertEquals(0, issues.size, "choice 条件引用变量时 UNUSED_VAR 数量应为 0")
    }

    @Test
    fun condReadInJumpNoWarning() {
        val src = """
            scene start:
              set flag = 1
              jump -> a if flag > 0
              end
            scene a:
              end
        """.trimIndent()

        val issues = unusedVarIssues(src)

        assertTrue(
            issues.isEmpty(),
            "flag 在 jump 条件中被引用应算作使用，不应报 UNUSED_VAR，实际: $issues"
        )
        assertEquals(0, issues.size, "jump 条件引用变量时 UNUSED_VAR 数量应为 0")
    }

    @Test
    fun readInSetRhsCountsAsUse() {
        val src = """
            scene start:
              set a = 1
              set b = a + 1
              text: "{b}"
              end
        """.trimIndent()

        val issues = unusedVarIssues(src)

        assertTrue(
            issues.isEmpty(),
            "a 在 b 的赋值表达式里被引用应算作使用，不应报 UNUSED_VAR，实际: $issues"
        )
        assertEquals(0, issues.size, "赋值表达式右侧引用变量时 UNUSED_VAR 数量应为 0")
    }

    @Test
    fun readInTextPlaceholderCountsAsUse() {
        val src = """
            scene start:
              set hp = 100
              text: "血量 {hp}"
              end
        """.trimIndent()

        val issues = unusedVarIssues(src)

        assertTrue(
            issues.isEmpty(),
            "hp 在文本占位符中被引用应算作使用，不应报 UNUSED_VAR，实际: $issues"
        )
        assertEquals(0, issues.size, "文本占位符引用变量时 UNUSED_VAR 数量应为 0")
    }
}