package com.interlude

import com.interlude.dsl.Parser
import com.interlude.lint.Report
import com.interlude.lint.Severity
import com.interlude.lint.Validator
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class EndToEndTest {

    private val source: String =
        javaClass.classLoader.getResource("scripts/sample.interlude")!!.readText()

    @Test
    fun `sample script parses to nine scenes with prologue entry`() {
        val story = Parser(source).parse()

        assertEquals(9, story.scenes.size, "sample.interlude should contain exactly 9 scenes")
        val entry = story.entry
        assertTrue(entry != null, "story should have a non-null entry scene")
        assertEquals("prologue", entry!!.id, "entry scene id should be \"prologue\"")
    }

    @Test
    fun `sample script yields exactly six known issues`() {
        val story = Parser(source).parse()
        val issues = Validator.validate(story)

        assertEquals(6, issues.size, "sample.interlude should yield exactly 6 issues")

        val first = issues[0]
        assertEquals(Severity.ERROR, first.severity)
        assertEquals("UNINIT_VAR", first.code)
        assertEquals("hall", first.sceneId)
        assertEquals(13, first.line)
        assertTrue(first.message.contains("has_key"), "first issue message should mention has_key")

        val second = issues[1]
        assertEquals(Severity.WARNING, second.severity)
        assertEquals("UNUSED_VAR", second.code)
        assertEquals("hall", second.sceneId)
        assertEquals(11, second.line)
        assertTrue(second.message.contains("met_stranger"), "second issue message should mention met_stranger")

        val third = issues[2]
        assertEquals(Severity.WARNING, third.severity)
        assertEquals("DEAD_END", third.code)
        assertEquals("orphan", third.sceneId)
        assertEquals(37, third.line)

        val fourth = issues[3]
        assertEquals(Severity.WARNING, fourth.severity)
        assertEquals("UNREACHABLE", fourth.code)
        assertEquals("orphan", fourth.sceneId)
        assertEquals(37, fourth.line)

        val fifth = issues[4]
        assertEquals(Severity.WARNING, fifth.severity)
        assertEquals("DEAD_END", fifth.code)
        assertEquals("deadend", fifth.sceneId)
        assertEquals(40, fifth.line)

        val sixth = issues[5]
        assertEquals(Severity.WARNING, sixth.severity)
        assertEquals("UNREACHABLE", sixth.code)
        assertEquals("deadend", sixth.sceneId)
        assertEquals(40, sixth.line)
    }

    @Test
    fun `text report covers the full chain deterministically`() {
        val story = Parser(source).parse()
        val issues = Validator.validate(story)
        val text = Report.formatText(issues)
        val lines = text.lines()

        assertEquals(
            "issues: 6 (errors: 1, warnings: 5)",
            lines.first(),
            "text report header must reflect 6 issues, 1 error, 5 warnings"
        )
        assertTrue(
            lines.any { it.startsWith("[ERROR] UNINIT_VAR hall:13 ") },
            "text report should contain the ERROR UNINIT_VAR hall:13 line"
        )
        assertTrue(
            lines.any { it.startsWith("[WARNING] UNUSED_VAR hall:11 ") },
            "text report should contain the WARNING UNUSED_VAR hall:11 line"
        )
        assertTrue(
            lines.any { it.startsWith("[WARNING] DEAD_END orphan:37 ") },
            "text report should contain the WARNING DEAD_END orphan:37 line"
        )
        assertTrue(
            lines.any { it.startsWith("[WARNING] UNREACHABLE deadend:40 ") },
            "text report should contain the WARNING UNREACHABLE deadend:40 line"
        )
    }

    @Test
    fun `json report carries summary and all six codes`() {
        val story = Parser(source).parse()
        val issues = Validator.validate(story)
        val json = Report.formatJson(issues)

        assertTrue(json.contains("\"issues\":6"))
        assertTrue(json.contains("\"errors\":1"))
        assertTrue(json.contains("\"warnings\":5"))
        assertTrue(json.contains("\"code\":\"UNINIT_VAR\""))
        assertTrue(json.contains("\"code\":\"UNUSED_VAR\""))
        assertTrue(json.contains("\"code\":\"DEAD_END\""))
        assertTrue(json.contains("\"code\":\"UNREACHABLE\""))
    }
}
