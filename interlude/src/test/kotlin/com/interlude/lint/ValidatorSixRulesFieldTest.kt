package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorSixRulesFieldTest {

    private val source = """scene start:
  set a = b
  choice "去" -> nowhere if 1 > 2
  set zzz = 9
  set zzz = 10
  text: "{a}"
  end

scene lonely:
  set q = 1
  text: "hi"
  end
""".trimIndent()

    private fun validateSource(): List<Issue> {
        val story = Parser(source).parse()
        return Validator.validate(story)
    }

    @Test
    fun allSixCodesPresent() {
        val issues = validateSource()
        val codes = issues.map { it.code }.toSet()
        assertEquals(
            setOf("UNINIT_VAR", "UNDEFINED_TARGET", "ALWAYS_FALSE", "UNREACHABLE", "UNUSED_VAR"),
            codes,
            "六规则同场交互时，报告应恰好包含这五种 code，DEAD_END 不应出现"
        )
        assertFalse(codes.contains("DEAD_END"), "start 有 choice 出口且以 end 结尾，lonely 以 end 结尾，均不应产生 DEAD_END")
    }

    @Test
    fun countsExact() {
        val issues = validateSource()
        val byCode = issues.groupingBy { it.code }.eachCount()
        assertEquals(1, byCode["UNINIT_VAR"], "b 被赋值表达式引用却从未 set，UNINIT_VAR 应恰好 1 条")
        assertEquals(1, byCode["UNDEFINED_TARGET"], "choice 目标 nowhere 不存在，UNDEFINED_TARGET 应恰好 1 条")
        assertEquals(1, byCode["ALWAYS_FALSE"], "条件 1 > 2 纯字面量恒假，ALWAYS_FALSE 应恰好 1 条")
        assertEquals(1, byCode["UNREACHABLE"], "lonely 从 start 不可达，UNREACHABLE 应恰好 1 条")
        assertEquals(2, byCode["UNUSED_VAR"], "zzz、q 被 set 后从未使用（a 在行6文本占位符中被引用），UNUSED_VAR 应恰好 2 条")
        assertEquals(6, issues.size, "六规则同场合计应产生 6 条报告")
    }

    @Test
    fun dedupZzzSingleLine4() {
        val issues = validateSource()
        val zzzIssues = issues.filter { it.code == "UNUSED_VAR" && it.message.contains("zzz") }
        assertEquals(1, zzzIssues.size, "zzz 被两次 set 但从未引用，UNUSED_VAR 去重后应恰好 1 条")
        assertEquals(4, zzzIssues[0].line, "去重后 zzz 的 UNUSED_VAR 行号应取首次 set 的行 4")
        assertEquals(Severity.WARNING, zzzIssues[0].severity, "UNUSED_VAR 严重级别应为 WARNING")
    }

    @Test
    fun fullOrder() {
        val issues = validateSource()
        val pairs = issues.map { it.code to it.line }
        val expected = listOf(
            "UNINIT_VAR" to 2,
            "UNDEFINED_TARGET" to 3,
            "ALWAYS_FALSE" to 3,
            "UNUSED_VAR" to 4,
            "UNREACHABLE" to 9,
            "UNUSED_VAR" to 10
        )
        val sorted = issues
            .sortedWith(compareBy({ it.severity.ordinal }, { it.line }))
            .map { it.code to it.line }
        assertEquals(expected, sorted, "按 severity 后 line 排序的 (code,line) 序列应符合推导")
        assertTrue(issues.isNotEmpty(), "报告列表不应为空")
    }
}