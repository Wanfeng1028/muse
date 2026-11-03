package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertFailsWith

class ReplayAnalyzerBoundaryTest {

    @Test
    fun emptyEventsThrows() {
        val ex = assertFailsWith<IllegalArgumentException> {
            ReplayAnalyzer.buildReport(null, emptyList())
        }
        assertEquals("事件列表为空，至少需要一个 SessionStart", ex.message, "空事件列表应抛出指定消息")
    }

    @Test
    fun firstNotSessionStartThrows() {
        val ex = assertFailsWith<IllegalArgumentException> {
            ReplayAnalyzer.buildReport(null, listOf(SceneEnter("a", "t")))
        }
        assertEquals("第一个事件必须是 SessionStart", ex.message, "首元素非 SessionStart 应抛出指定消息")
    }

    @Test
    fun noSessionEndNulls() {
        val events = listOf(
            SessionStart("t1", "s", 1, "t0"),
            SceneEnter("a", "t1"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        assertNull(report.endedAt, "无 SessionEnd 时 endedAt 应为 null")
        assertNull(report.outcome, "无 SessionEnd 时 outcome 应为 null")
        assertNull(report.winner, "无 SessionEnd 时 winner 应为 null")
        assertEquals(2, report.timeline.size, "时间线应保留全部事件")
        assertEquals("t1", report.sessionId, "sessionId 应来自首个 SessionStart")
        assertEquals("s", report.scriptFile, "scriptFile 应来自首个 SessionStart")
        assertEquals("t0", report.startedAt, "startedAt 应来自首个 SessionStart 的 at")
    }

    @Test
    fun lastSessionEndWins() {
        val events = listOf(
            SessionStart("t1", "s", 1, "t0"),
            SessionEnd("坏结局", null, "t1"),
            SessionEnd("好结局", "阿强", "t2"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        assertEquals("好结局", report.outcome, "应取最后一个 SessionEnd 的 outcome")
        assertEquals("阿强", report.winner, "应取最后一个 SessionEnd 的 winner")
        assertEquals("t2", report.endedAt, "应取最后一个 SessionEnd 的 at")
        assertEquals(3, report.timeline.size, "时间线应保留全部事件")
    }
}