package com.interlude.lint

import com.interlude.dsl.Parser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ValidatorUnusedVarDedupMessageTest {

    private fun issuesOf(code: String, source: String): List<Issue> =
        Validator.validate(Parser(source).parse()).filter { it.code == code }

    @Test
    fun repeatedSetsAcrossScenesOneReport() {
        val source = """
scene start:
  set dup = 1
  jump -> b
scene b:
  set dup = 2
  end
""".trimIndent()

        val unused = issuesOf("UNUSED_VAR", source)
        assertEquals(1, unused.size, "同一变量跨场景多次 set 只应报告一次 UNUSED_VAR")
        assertEquals(2, unused[0].line, "行号应为首次 set 的行 2")
        assertEquals("start", unused[0].sceneId, "sceneId 应为首次 set 所在的 start 场景")
        assertEquals(Severity.WARNING, unused[0].severity, "UNUSED_VAR 严重级别应为 WARNING")
    }

    @Test
    fun messageFormatContract() {
        val source = """
scene start:
  set myvar = 1
  end
""".trimIndent()

        val unused = issuesOf("UNUSED_VAR", source)
        assertEquals(1, unused.size, "应恰好报告一条 UNUSED_VAR")
        val issue = unused[0]
        assertEquals("UNUSED_VAR", issue.code, "code 必须为 UNUSED_VAR")
        assertEquals(Severity.WARNING, issue.severity, "severity 必须为 WARNING")
        assertEquals(
            "变量 'myvar' 被 set 赋值后从未使用",
            issue.message,
            "message 必须精确匹配约定格式"
        )
    }

    @Test
    fun mixedUsedUnusedOnlyUnusedReported() {
        val source = """
scene start:
  set used1 = 1
  set dead1 = 2
  set used2 = used1
  text: "{used2}"
  end
""".trimIndent()

        val unused = issuesOf("UNUSED_VAR", source)
        assertEquals(1, unused.size, "只有 dead1 从未使用，应恰好报告一条 UNUSED_VAR")
        assertTrue(unused[0].message.contains("dead1"), "报告的消息应包含未使用变量名 dead1")
        assertFalse(
            unused.any { it.message.contains("used1") || it.message.contains("used2") },
            "used1 与 used2 均被引用，不应出现在 UNUSED_VAR 报告中"
        )
    }
}