package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ReplayMarkdownEmptyTimelineTest {

    private fun emptyTimelineReport(): ReplayReport {
        val start = SessionStart(
            sessionId = "t1",
            scriptFile = "s.interlude",
            playerCount = 2,
            at = "2026-10-16T20:00:00+08:00",
        )
        return ReplayReport(
            sessionId = "t1",
            scriptFile = "s.interlude",
            startedAt = "2026-10-16T20:00:00+08:00",
            endedAt = null,
            timeline = listOf(start),
            decisionPoints = emptyList(),
            voteRounds = emptyList(),
            playerStats = emptyList(),
            keyMoments = emptyList(),
            outcome = null,
            winner = null,
            warnings = emptyList(),
        )
    }

    @Test
    fun emptyTimelineFallback() {
        val report = emptyTimelineReport().copy(timeline = emptyList())
        val md = ReplayMarkdown.render(report)
        assertTrue(
            md.contains("本局无事件记录。"),
            "timeline 为空时渲染应输出空时间线降级文案",
        )
    }

    @Test
    fun headerFieldsRendered() {
        val report = emptyTimelineReport()
        val md = ReplayMarkdown.render(report)
        assertTrue(md.contains("- 对局：`t1`"), "头部应渲染对局 ID t1")
        assertTrue(md.contains("- 剧本：`s.interlude`"), "头部应渲染剧本文件名 s.interlude")
        assertTrue(md.contains("- 结束时间：未记录"), "endedAt 为 null 时应渲染未记录")
        assertTrue(md.contains("- 事件总数：1"), "timeline 只含一个 SessionStart，事件总数应为 1")
    }

    @Test
    fun outcomeFallback() {
        val report = emptyTimelineReport()
        val md = ReplayMarkdown.render(report)
        assertTrue(md.contains("结果：未记录"), "outcome 为 null 时应渲染未记录")
        assertFalse(md.contains("胜者："), "winner 为 null 时不应渲染胜者行")
    }

    @Test
    fun noWarningsSection() {
        val report = emptyTimelineReport()
        val md = ReplayMarkdown.render(report)
        assertFalse(md.contains("## 数据问题"), "warnings 为空时不应渲染数据问题章节")
    }
}