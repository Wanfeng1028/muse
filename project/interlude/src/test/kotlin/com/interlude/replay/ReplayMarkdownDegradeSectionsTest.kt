package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ReplayMarkdownDegradeSectionsTest {

    private fun baseReport(
        timeline: List<SessionEvent>,
        endedAt: String? = null,
        outcome: String? = null,
        winner: String? = null,
    ): ReplayReport = ReplayReport(
        sessionId = "t1",
        scriptFile = "s.interlude",
        startedAt = "2026-10-16T20:00:00+08:00",
        endedAt = endedAt,
        timeline = timeline,
        decisionPoints = emptyList(),
        voteRounds = emptyList(),
        playerStats = emptyList(),
        keyMoments = emptyList(),
        outcome = outcome,
        winner = winner,
        warnings = emptyList(),
    )

    private fun minimalTimeline(): List<SessionEvent> = listOf(
        SessionStart(
            sessionId = "t1",
            scriptFile = "s.interlude",
            playerCount = 2,
            at = "2026-10-16T20:00:00+08:00",
        ),
        SceneEnter(sceneId = "a", at = "2026-10-16T20:00:05+08:00"),
    )

    @Test
    fun noDecisionPointsFallback() {
        val report = baseReport(minimalTimeline())
        val text = ReplayMarkdown.render(report)
        assertTrue(
            text.contains("本局没有记录到抉择点。"),
            "抉择点为空时应输出降级文案，实际：$text",
        )
        assertTrue(text.contains("## 抉择点复盘"), "应保留抉择点复盘标题，实际：$text")
    }

    @Test
    fun noVotesFallback() {
        val report = baseReport(minimalTimeline())
        val text = ReplayMarkdown.render(report)
        assertTrue(
            text.contains("本局无投票记录。"),
            "投票轮次为空时应输出降级文案，实际：$text",
        )
        assertTrue(text.contains("## 投票与出局"), "应保留投票与出局标题，实际：$text")
    }

    @Test
    fun noPlayerStatsFallback() {
        val report = baseReport(minimalTimeline())
        val text = ReplayMarkdown.render(report)
        assertTrue(text.contains("## MVP 评选"), "应包含 MVP 评选标题，实际：$text")
        assertTrue(
            text.contains("本局无玩家投票数据，MVP 评选略。"),
            "玩家统计为空时应输出 MVP 降级文案，实际：$text",
        )
        assertFalse(
            text.contains("| 玩家 | 投出 | 被投 | 出局轮次 | 你的 MVP 一票 |"),
            "玩家统计为空时不应渲染 MVP 表头，实际：$text",
        )
    }

    @Test
    fun noKeyMomentsFallback() {
        val report = baseReport(minimalTimeline())
        val text = ReplayMarkdown.render(report)
        assertTrue(text.contains("## 关键标注"), "应包含关键标注标题，实际：$text")
        val sectionIndex = text.indexOf("## 关键标注")
        val afterSection = text.substring(sectionIndex)
        assertTrue(
            afterSection.contains("无。"),
            "关键标注为空时应输出“无。”，实际：$text",
        )
    }

    @Test
    fun sessionEndRendered() {
        val timeline = minimalTimeline() + SessionEnd(
            outcome = "好结局",
            winner = "阿强",
            at = "t3",
        )
        val report = baseReport(
            timeline = timeline,
            endedAt = "t3",
            outcome = "好结局",
            winner = "阿强",
        )
        val text = ReplayMarkdown.render(report)
        assertTrue(
            text.contains("对局结束：好结局"),
            "时间线应渲染 SessionEnd 行，实际：$text",
        )
        assertTrue(text.contains("胜者：阿强"), "应渲染胜者行，实际：$text")
        assertTrue(text.contains("结果：好结局"), "应渲染对局结果，实际：$text")
        assertEquals(3, report.timeline.size, "时间线应包含 3 个事件")
        assertEquals("t3", report.endedAt, "endedAt 应为 t3")
    }
}