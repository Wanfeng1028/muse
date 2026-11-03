package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ValidatorSortContractTest {

    @Test
    fun errorsBeforeWarningsByLine() {
        val source = """
            scene start:
              set a = b
              choice "去" -> nowhere
              set u1 = 1
              set u2 = 2
              text: "{a}"
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val codes = issues.map { it.code }
        val lines = issues.map { it.line }

        assertEquals(
            listOf("UNINIT_VAR", "UNDEFINED_TARGET", "UNUSED_VAR", "UNUSED_VAR"),
            codes,
            "ERROR 应排在 WARNING 之前，且同类按行号升序"
        )
        assertEquals(
            listOf(2, 3, 4, 5),
            lines,
            "行号序列应为 2,3,4,5"
        )
    }

    @Test
    fun warningsSortedByLineAcrossScenes() {
        val source = """
            scene start:
              text: "x"
              jump -> tail
            scene mid:
              end
            scene tail:
              set zz = 1
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        assertTrue(issues.isNotEmpty(), "应产生告警问题列表非空")
        assertTrue(
            issues.all { it.severity == Severity.WARNING },
            "所有问题都应为 WARNING 级别"
        )
        assertEquals(2, issues.size, "应恰好有 2 条 WARNING")

        assertEquals(
            listOf(4, 7),
            issues.map { it.line },
            "跨场景 WARNING 应按行号升序排列为 4,7"
        )
        assertEquals(
            listOf("UNREACHABLE", "UNUSED_VAR"),
            issues.map { it.code },
            "code 序列应为 UNREACHABLE（行4）后跟 UNUSED_VAR（行7）"
        )
    }

    @Test
    fun stableForSameSeveritySameLine() {
        val source = """
            scene start:
              set a = b + c
              end
        """.trimIndent()

        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        val uninit = issues.filter { it.code == "UNINIT_VAR" }
        assertEquals(2, uninit.size, "应恰好有 2 条 UNINIT_VAR")
        assertTrue(
            uninit.all { it.line == 2 },
            "两条 UNINIT_VAR 都应位于行 2"
        )

        assertTrue(
            issues[0].message.contains("b"),
            "排序稳定，第一条消息应包含变量 b"
        )
        assertTrue(
            issues[1].message.contains("c"),
            "排序稳定，第二条消息应包含变量 c"
        )
    }
}