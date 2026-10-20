package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarCondChainTest {

    @Test
    fun choiceCondUseThenUnconditionalJump() {
        val source = """
            |scene start:
            |  set c = 0
            |  choice "去" -> a if c == 0
            |  jump -> b
            |
            |scene a:
            |  end
            |
            |scene b:
            |  end
        """.trimMargin()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)
        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(
            unused.isEmpty(),
            "choice 条件中引用的变量 c 应算作使用，不应产生 UNUSED_VAR，实际: $unused"
        )
    }

    @Test
    fun jumpCondUse() {
        val source = """
            |scene start:
            |  set n = 3
            |  jump -> a if n > 1
            |  jump -> b
            |
            |scene a:
            |  end
            |
            |scene b:
            |  end
        """.trimMargin()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)
        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertTrue(
            unused.isEmpty(),
            "jump 条件中引用的变量 n 应算作使用，不应产生 UNUSED_VAR，实际: $unused"
        )
    }

    @Test
    fun condVarUnusedElsewhereStillUsed() {
        val source = """
            |scene start:
            |  set flag = 1
            |  set other = 2
            |  choice "去" -> a if flag == 1
            |  jump -> b
            |
            |scene a:
            |  end
            |
            |scene b:
            |  end
        """.trimMargin()
        val story = Parser(source).parse()
        val issues = Validator.validate(story)
        val unused = issues.filter { it.code == "UNUSED_VAR" }
        assertEquals(
            1,
            unused.size,
            "只有 other 从未被引用，应恰好报告 1 条 UNUSED_VAR，实际: $unused"
        )
        val issue = unused.first()
        assertEquals(
            Severity.WARNING,
            issue.severity,
            "UNUSED_VAR 的严重级别应为 WARNING"
        )
        assertEquals(
            "UNUSED_VAR",
            issue.code,
            "报告的问题代码应为 UNUSED_VAR"
        )
        assertTrue(
            issue.message.contains("other"),
            "UNUSED_VAR 的 message 应包含变量名 other，实际: ${issue.message}"
        )
        assertFalse(
            issue.message.contains("flag"),
            "flag 在 choice 条件中被引用，不应出现在 UNUSED_VAR 的 message 中，实际: ${issue.message}"
        )
    }
}