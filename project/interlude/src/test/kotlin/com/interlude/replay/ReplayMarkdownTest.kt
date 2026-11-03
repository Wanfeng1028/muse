package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertTrue

class ReplayMarkdownTest {

    private fun buildBasicReport(): ReplayReport {
        val events = listOf(
            SessionStart(sessionId = "demo-001", scriptFile = "sample.interlude", playerCount = 1, at = "2026-10-16T20:00:00+08:00"),
            SceneEnter(sceneId = "prologue", at = "2026-10-16T20:00:05+08:00"),
            ChoiceMade(
                sceneId = "prologue",
                label = "走向候车室",
                target = "hall",
                alternatives = listOf(Alternative("留在站台", "platform")),
                at = "2026-10-16T20:00:40+08:00",
            ),
            KeyMoment(note = "关键抉择", sceneId = "hall", at = "2026-10-16T20:01:10+08:00"),
            SessionEnd(outcome = "抵达 ending_a", winner = null, at = "2026-10-16T20:02:10+08:00"),
        )
        return ReplayAnalyzer.buildReport(null, events)
    }

    @Test
    fun containsHeaderAndSessionId() {
        val md = ReplayMarkdown.render(buildBasicReport())
        assertTrue(md.startsWith("# 复盘报告"))
        assertTrue(md.contains("demo-001"))
        assertTrue(md.contains("sample.interlude"))
    }

    @Test
    fun timelineSectionListsEventsInOrder() {
        val md = ReplayMarkdown.render(buildBasicReport())
        assertTrue(md.contains("## 对局时间线"))
        val idxStart = md.indexOf("对局开始（1 人）")
        val idxScene = md.indexOf("进入场景 prologue")
        val idxChoice = md.indexOf("在 prologue 选择「走向候车室」→ hall")
        val idxEnd = md.indexOf("对局结束：抵达 ending_a")
        assertTrue(idxStart in 0 until idxScene)
        assertTrue(idxScene in 0 until idxChoice)
        assertTrue(idxChoice in 0 until idxEnd)
    }

    @Test
    fun decisionPointSectionContainsAlternatives() {
        val md = ReplayMarkdown.render(buildBasicReport())
        assertTrue(md.contains("## 抉择点复盘"))
        assertTrue(md.contains("没走的路"))
        assertTrue(md.contains("- 留在站台 → platform"))
        assertTrue(md.contains("选择了：走向候车室 → hall"))
    }

    @Test
    fun noVotesShowsEmptyMessage() {
        val md = ReplayMarkdown.render(buildBasicReport())
        assertTrue(md.contains("## 投票与出局"))
        assertTrue(md.contains("本局无投票记录。"))
    }

    @Test
    fun votesShowMvpTableWithPlayers() {
        val events = listOf(
            SessionStart(sessionId = "s", scriptFile = "x", playerCount = 3, at = "t0"),
            VoteCast(voter = "alice", target = "bob", round = 1, at = "t1"),
            VoteCast(voter = "carol", target = "bob", round = 1, at = "t2"),
            Elimination(player = "bob", reason = "票数最多", round = 1, at = "t3"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        val md = ReplayMarkdown.render(report)
        assertTrue(md.contains("## MVP 评选"))
        assertTrue(md.contains("| 玩家 | 投出 | 被投 | 出局轮次 | 你的 MVP 一票 |"))
        assertTrue(md.contains("alice"))
        assertTrue(md.contains("bob"))
        assertTrue(md.contains("carol"))
        assertTrue(md.contains("出局：bob（票数最多）"))
    }

    @Test
    fun noPlayerDataShowsMvpSkipped() {
        val md = ReplayMarkdown.render(buildBasicReport())
        assertTrue(md.contains("MVP 评选略"))
    }

    @Test
    fun warningsSectionAppearsWhenPresent() {
        val events = listOf(
            SessionStart(sessionId = "s", scriptFile = "x", playerCount = 1, at = "t0"),
            SceneEnter(sceneId = "ghost", at = "t1"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        // story=null 时不会产生 warning，这里手工用带 story 的方式不行，所以直接构造带 warning 的 report
        val reportWithWarning = report.copy(
            warnings = listOf("事件 events[1] 引用的场景 'ghost' 在剧本中不存在")
        )
        val md = ReplayMarkdown.render(reportWithWarning)
        assertTrue(md.contains("## 数据问题"))
        assertTrue(md.contains("ghost"))
    }

    @Test
    fun keyMomentsSectionListsNotes() {
        val md = ReplayMarkdown.render(buildBasicReport())
        assertTrue(md.contains("## 关键标注"))
        assertTrue(md.contains("关键抉择"))
        assertTrue(md.contains("（场景 hall）"))
    }

    @Test
    fun outcomeSectionShowsResult() {
        val md = ReplayMarkdown.render(buildBasicReport())
        assertTrue(md.contains("## 对局结果"))
        assertTrue(md.contains("抵达 ending_a"))
    }
}
