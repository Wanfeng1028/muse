package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ReplayMarkdownBoundaryTest {

    private val t0 = "2026-10-20T10:00:00+08:00"

    private fun emptyReport(
        sessionId: String = "sess-1",
        scriptFile: String = "script.md",
        startedAt: String = t0,
        endedAt: String? = null,
        timeline: List<SessionEvent> = emptyList(),
        decisionPoints: List<DecisionPoint> = emptyList(),
        voteRounds: List<VoteRound> = emptyList(),
        playerStats: List<PlayerStats> = emptyList(),
        keyMoments: List<KeyMoment> = emptyList(),
        outcome: String? = null,
        winner: String? = null,
        warnings: List<String> = emptyList(),
    ) = ReplayReport(
        sessionId = sessionId,
        scriptFile = scriptFile,
        startedAt = startedAt,
        endedAt = endedAt,
        timeline = timeline,
        decisionPoints = decisionPoints,
        voteRounds = voteRounds,
        playerStats = playerStats,
        keyMoments = keyMoments,
        outcome = outcome,
        winner = winner,
        warnings = warnings,
    )

    @Test
    fun emptyTimelineRendersPlaceholderAndHeader() {
        val report = emptyReport(timeline = emptyList())
        val out = ReplayMarkdown.render(report)
        assertTrue(out.startsWith("# 复盘报告"))
        assertTrue(out.contains("本局无事件记录。"))
        assertTrue(out.contains("- 事件总数：0\n"))
    }

    @Test
    fun fullyEmptyReportEmitsAllPlaceholdersAndNoWarningsSection() {
        val report = emptyReport()
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("本局没有记录到抉择点。"))
        assertTrue(out.contains("本局无投票记录。"))
        assertTrue(out.contains("本局无玩家投票数据，MVP 评选略。"))
        assertTrue(out.contains("无。"))
        assertTrue(out.contains("结束时间：未记录"))
        assertTrue(out.contains("结果：未记录"))
        assertTrue(!out.contains("## 数据问题"))
    }

    @Test
    fun sessionIdWithBackticksIsPassedThroughVerbatim() {
        val weird = "sess`id`007"
        val report = emptyReport(sessionId = weird)
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("- 对局：`$weird`\n"))
    }

    @Test
    fun playerNameWithPipeBreaksTableButIsPassedThrough() {
        val report = emptyReport(
            playerStats = listOf(
                PlayerStats(
                    player = "张|三",
                    votesCast = 2,
                    votesReceived = 1,
                    eliminatedRound = null,
                )
            )
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("| 张|三 | 2 | 1 | - |  |\n"))
    }

    @Test
    fun keyMomentNoteWithNewlineIsNotEscaped() {
        val report = emptyReport(
            keyMoments = listOf(
                KeyMoment(
                    note = "第一行\n第二行",
                    sceneId = null,
                    at = t0,
                )
            )
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("第一行"))
        assertTrue(out.contains("第二行"))
        assertTrue(out.contains("- $t0 第一行\n第二行\n"))
    }

    @Test
    fun veryLongNoteProducesLongOutput() {
        val note = "注".repeat(10000)
        val report = emptyReport(
            keyMoments = listOf(KeyMoment(note = note, sceneId = null, at = t0))
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.length >= 10000)
        assertTrue(out.contains(note))
    }

    @Test
    fun hugeTimelineOf5000SceneEntersRendersCompletely() {
        val events = ArrayList<SessionEvent>(5002)
        events.add(
            SessionStart(
                sessionId = "big",
                scriptFile = "big.md",
                playerCount = 1,
                at = t0,
            )
        )
        repeat(5000) { i ->
            events.add(SceneEnter(sceneId = "scene-$i", at = t0))
        }
        events.add(SessionEnd(outcome = "结束", winner = null, at = t0))

        val report = emptyReport(
            sessionId = "big",
            scriptFile = "big.md",
            endedAt = t0,
            timeline = events,
            outcome = "结束",
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("- 事件总数：5002\n"))
        assertTrue(out.contains("1. 对局开始（1 人）\n"))
        assertTrue(out.contains("5002. 对局结束：结束\n"))
    }

    @Test
    fun cjkTextIsPassedThroughVerbatim() {
        val report = emptyReport(
            sessionId = "对局-日本語-한국어-001",
            decisionPoints = listOf(
                DecisionPoint(
                    sceneId = "场景A",
                    sceneLine = 3,
                    sceneText = "",
                    chosenLabel = "選択肢",
                    chosenTarget = "场景B",
                    alternatives = emptyList(),
                )
            ),
            keyMoments = listOf(
                KeyMoment(note = "한글 메모", sceneId = null, at = t0)
            ),
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("- 对局：`对局-日本語-한국어-001`\n"))
        assertTrue(out.contains("选择了：選択肢 → 场景B\n"))
        assertTrue(out.contains("- $t0 한글 메모\n"))
    }

    @Test
    fun emojiInNoteIsPassedThroughVerbatim() {
        val note = "🎬 高光时刻 🔥"
        val report = emptyReport(
            keyMoments = listOf(KeyMoment(note = note, sceneId = null, at = t0))
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains(note))
        assertTrue(out.contains("- $t0 $note\n"))
    }

    @Test
    fun extremelyLongSessionIdRendersWithoutError() {
        val longId = "s".repeat(500)
        val report = emptyReport(sessionId = longId)
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("- 对局：`$longId`\n"))
    }

    @Test
    fun sceneTextWithMarkdownSpecialCharsIsPassedThrough() {
        val text = "# 标题\n> 引用"
        val report = emptyReport(
            decisionPoints = listOf(
                DecisionPoint(
                    sceneId = "s1",
                    sceneLine = 1,
                    sceneText = text,
                    chosenLabel = "L",
                    chosenTarget = "T",
                    alternatives = emptyList(),
                )
            )
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("> # 标题\n> 引用\n\n"))
    }

    @Test
    fun warningsSectionRenderedWithSpecialChars() {
        val warning = "事件 events[2] 引用 `x|y`"
        val report = emptyReport(warnings = listOf(warning))
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("## 数据问题"))
        assertTrue(out.contains("- $warning\n"))
    }

    @Test
    fun timelineNumberingIsOneBasedAndSequential() {
        val events = listOf<SessionEvent>(
            SessionStart(sessionId = "s", scriptFile = "f", playerCount = 3, at = t0),
            SceneEnter(sceneId = "a", at = t0),
            SceneEnter(sceneId = "b", at = t0),
        )
        val report = emptyReport(
            sessionId = "s",
            scriptFile = "f",
            timeline = events,
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("1. 对局开始（3 人）\n"))
        assertTrue(out.contains("2. 进入场景 a\n"))
        assertTrue(out.contains("3. 进入场景 b\n"))
        assertTrue(!out.contains("0. "))
    }

    @Test
    fun decisionPointWithoutAlternativesRendersEmptyAlternativeList() {
        val report = emptyReport(
            decisionPoints = listOf(
                DecisionPoint(
                    sceneId = "scene-x",
                    sceneLine = -1,
                    sceneText = "",
                    chosenLabel = "A",
                    chosenTarget = "B",
                    alternatives = emptyList(),
                )
            )
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("### 1. scene-x（第 -1 行）\n"))
        assertTrue(out.contains("选择了：A → B\n"))
        assertTrue(out.contains("没走的路：\n"))
        assertTrue(!out.contains("- A → B\n"))
    }

    @Test
    fun voteRoundWithEliminationAndNullEndedAtRendersConsistently() {
        val report = emptyReport(
            endedAt = null,
            outcome = null,
            winner = null,
            voteRounds = listOf(
                VoteRound(
                    round = 1,
                    votes = listOf(
                        VoteCast(voter = "A", target = "B", round = 1, at = t0),
                    ),
                    eliminated = Elimination(player = "B", reason = "票出", round = 1, at = t0),
                )
            ),
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("### 第 1 轮\n"))
        assertTrue(out.contains("- A → B\n"))
        assertTrue(out.contains("出局：B（票出）\n"))
        assertTrue(out.contains("结束时间：未记录"))
        assertTrue(out.contains("结果：未记录"))
    }

    @Test
    fun winnerLineEmittedOnlyWhenWinnerNonNull() {
        val withoutWinner = ReplayMarkdown.render(
            emptyReport(outcome = "平局", winner = null)
        )
        assertTrue(withoutWinner.contains("结果：平局\n"))
        assertTrue(!withoutWinner.contains("胜者："))

        val withWinner = ReplayMarkdown.render(
            emptyReport(outcome = "分出胜负", winner = "玩家A")
        )
        assertTrue(withWinner.contains("结果：分出胜负\n"))
        assertTrue(withWinner.contains("胜者：玩家A\n"))
    }

    @Test
    fun mvpTableHeaderAndRowShapeAreStable() {
        val report = emptyReport(
            playerStats = listOf(
                PlayerStats(player = "P1", votesCast = 5, votesReceived = 3, eliminatedRound = 2),
                PlayerStats(player = "P2", votesCast = 0, votesReceived = 0, eliminatedRound = null),
            )
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("| 玩家 | 投出 | 被投 | 出局轮次 | 你的 MVP 一票 |\n"))
        assertTrue(out.contains("| --- | --- | --- | --- | --- |\n"))
        assertTrue(out.contains("| P1 | 5 | 3 | 2 |  |\n"))
        assertTrue(out.contains("| P2 | 0 | 0 | - |  |\n"))
    }

    @Test
    fun keyMomentWithSceneIdRendersSceneAnnotationForm() {
        val report = emptyReport(
            keyMoments = listOf(
                KeyMoment(note = "反转", sceneId = "s9", at = t0)
            )
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("- $t0 反转\n"))
    }

    @Test
    fun emptyTimelineWithPopulatedOtherSectionsStillRendersAllSections() {
        val report = emptyReport(
            timeline = emptyList(),
            decisionPoints = listOf(
                DecisionPoint(
                    sceneId = "s",
                    sceneLine = 1,
                    sceneText = "正文",
                    chosenLabel = "L",
                    chosenTarget = "T",
                    alternatives = listOf(Alternative(label = "X", target = "Y")),
                )
            ),
            voteRounds = emptyList(),
            playerStats = emptyList(),
            keyMoments = emptyList(),
        )
        val out = ReplayMarkdown.render(report)
        assertTrue(out.contains("本局无事件记录。"))
        assertTrue(out.contains("> 正文\n\n"))
        assertTrue(out.contains("- X → Y\n"))
        assertTrue(out.contains("本局无投票记录。"))
        assertTrue(out.contains("本局无玩家投票数据，MVP 评选略。"))
    }

    @Test
    fun outputIsDeterministicForSameInput() {
        val report = emptyReport(
            timeline = listOf(
                SessionStart(sessionId = "det", scriptFile = "f", playerCount = 2, at = t0),
                SceneEnter(sceneId = "a", at = t0),
            ),
            endedAt = t0,
            outcome = "完",
        )
        val first = ReplayMarkdown.render(report)
        val second = ReplayMarkdown.render(report)
        assertEquals(first, second)
    }
}

