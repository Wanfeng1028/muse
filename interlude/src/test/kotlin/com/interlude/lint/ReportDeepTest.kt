package com.interlude.lint

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ReportDeepTest {

    @Test
    fun `text empty list returns exact summary line`() {
        // 依据：formatText 首行为 `issues: N (errors: E, warnings: W)`，空列表 N=E=W=0
        assertEquals("issues: 0 (errors: 0, warnings: 0)", Report.formatText(emptyList()))
    }

    @Test
    fun `text counts and lines preserves input order`() {
        val issues = listOf(
            Issue(Severity.ERROR, "DEAD_END", "死路", "s1", 3),
            Issue(Severity.WARNING, "UNUSED_VAR", "未使用", "s2", 7)
        )
        val out = Report.formatText(issues)
        // 首行统计：2 条，1 个 ERROR，1 个 WARNING
        assertTrue(out.contains("issues: 2 (errors: 1, warnings: 1)"))
        // 每条格式：`[SEVERITY] CODE sceneId:line message`
        assertTrue(out.contains("[ERROR] DEAD_END s1:3 死路"))
        assertTrue(out.contains("[WARNING] UNUSED_VAR s2:7 未使用"))
        // 顺序与输入一致：ERROR 行出现在 WARNING 行之前
        assertTrue(out.indexOf("[ERROR] DEAD_END s1:3 死路") < out.indexOf("[WARNING] UNUSED_VAR s2:7 未使用"))
    }

    @Test
    fun `text only warnings counts zero errors`() {
        val issues = listOf(Issue(Severity.WARNING, "W1", "m", "s", 1))
        // 首行统计：1 条，0 个 ERROR，1 个 WARNING
        assertTrue(Report.formatText(issues).contains("issues: 1 (errors: 0, warnings: 1)"))
    }

    @Test
    fun `json empty list returns exact document`() {
        // 依据：summary 与空 issues 数组的确定输出
        assertEquals(
            "{\"summary\":{\"issues\":0,\"errors\":0,\"warnings\":0},\"issues\":[]}",
            Report.formatJson(emptyList())
        )
    }

    @Test
    fun `json structure contains expected fields and summary counts`() {
        val issues = listOf(Issue(Severity.ERROR, "C", "m", "s", 5))
        val out = Report.formatJson(issues)
        assertTrue(out.contains("\"severity\":\"ERROR\""))
        assertTrue(out.contains("\"code\":\"C\""))
        assertTrue(out.contains("\"scene\":\"s\""))
        assertTrue(out.contains("\"line\":5"))
        assertTrue(out.contains("\"message\":\"m\""))
        // summary 中 issues/errors/warnings 为 1/1/0
        assertTrue(out.contains("\"summary\":{\"issues\":1,\"errors\":1,\"warnings\":0}"))
    }

    @Test
    fun `json escapes quotes and backslash in message`() {
        // 依据：双引号→\"，反斜杠→\\
        val issues = listOf(Issue(Severity.ERROR, "C", "a\"b\\c", "s", 1))
        val out = Report.formatJson(issues)
        assertTrue(out.contains("\"message\":\"a\\\"b\\\\c\""))
    }

    @Test
    fun `json escapes newline and control char in message`() {
        // 依据：\n→\n，其他 <' ' 的字符→\uXXXX（小写 hex，前补 0）
        val issues = listOf(Issue(Severity.ERROR, "C", "x\ny\u0001z", "s", 1))
        val out = Report.formatJson(issues)
        assertTrue(out.contains("x\\ny\\u0001z"))
    }

    @Test
    fun `json multiple issues are comma separated in input order`() {
        val issues = listOf(
            Issue(Severity.ERROR, "A", "first", "s1", 1),
            Issue(Severity.WARNING, "B", "second", "s2", 2)
        )
        val out = Report.formatJson(issues)
        // join 逻辑：两个对象之间恰好一个 "},{" 分隔
        val separator = "},{"
        val firstIdx = out.indexOf(separator)
        assertTrue(firstIdx >= 0)
        assertTrue(out.indexOf(separator, firstIdx + 1) == -1)
        // 顺序与输入一致：first 出现在 second 之前
        assertTrue(out.indexOf("\"message\":\"first\"") < out.indexOf("\"message\":\"second\""))
    }
}
