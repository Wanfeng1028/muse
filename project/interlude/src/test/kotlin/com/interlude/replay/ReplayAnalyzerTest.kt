package com.interlude.replay

import com.interlude.dsl.Choice
import com.interlude.dsl.Scene
import com.interlude.dsl.Story
import com.interlude.dsl.Text
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ReplayAnalyzerTest {

    private fun sampleStory(): Story {
        // 构造最小剧本：prologue 有 text，hall 有 text，stranger 无 text，ending_a 有 text
        val prologue = Scene(
            id = "prologue",
            line = 1,
            statements = listOf(
                Text(line = 2, value = "雨。"),
                Choice(line = 3, label = "走向候车室", target = "hall", condition = null),
            ),
        )
        val hall = Scene(
            id = "hall",
            line = 10,
            statements = listOf(
                Text(line = 11, value = "厅。"),
                Choice(line = 12, label = "和陌生人搭话", target = "stranger", condition = null),
            ),
        )
        val stranger = Scene(
            id = "stranger",
            line = 20,
            statements = listOf(
                Choice(line = 21, label = "报上姓名", target = "ending_a", condition = null),
            ),
        )
        val endingA = Scene(
            id = "ending_a",
            line = 30,
            statements = listOf(Text(line = 31, value = "结束。")),
        )
        return Story(scenes = listOf(prologue, hall, stranger, endingA))
    }

    private fun startEvent(at: String = "t0"): SessionStart =
        SessionStart(sessionId = "s1", scriptFile = "a.interlude", playerCount = 2, at = at)

    @Test
    fun decisionPointsExtractedWithAlternatives() {
        val events = listOf(
            startEvent(),
            ChoiceMade(
                sceneId = "prologue",
                label = "走向候车室",
                target = "hall",
                alternatives = listOf(Alternative("留在站台", "platform")),
                at = "t1",
            ),
            ChoiceMade(
                sceneId = "hall",
                label = "和陌生人搭话",
                target = "stranger",
                alternatives = listOf(Alternative("推门离开", "exit")),
                at = "t2",
            ),
        )
        val report = ReplayAnalyzer.buildReport(sampleStory(), events)
        assertEquals(2, report.decisionPoints.size)
        assertEquals("走向候车室", report.decisionPoints[0].chosenLabel)
        assertEquals(listOf(Alternative("留在站台", "platform")), report.decisionPoints[0].alternatives)
        assertEquals("和陌生人搭话", report.decisionPoints[1].chosenLabel)
        assertEquals("exit", report.decisionPoints[1].alternatives[0].target)
    }

    @Test
    fun choiceMadeWithoutAlternativesIsNotDecisionPoint() {
        val events = listOf(
            startEvent(),
            ChoiceMade(
                sceneId = "prologue",
                label = "无备选",
                target = "hall",
                alternatives = emptyList(),
                at = "t1",
            ),
        )
        val report = ReplayAnalyzer.buildReport(sampleStory(), events)
        assertTrue(report.decisionPoints.isEmpty())
    }

    @Test
    fun sceneLineAndTextEnriched() {
        val events = listOf(
            startEvent(),
            ChoiceMade(
                sceneId = "hall",
                label = "和陌生人搭话",
                target = "stranger",
                alternatives = listOf(Alternative("推门离开", "exit")),
                at = "t1",
            ),
        )
        val report = ReplayAnalyzer.buildReport(sampleStory(), events)
        val dp = report.decisionPoints.single()
        assertEquals(10, dp.sceneLine)
        assertEquals("厅。", dp.sceneText)
    }

    @Test
    fun sceneWithoutTextEnrichedWithEmptyText() {
        val events = listOf(
            startEvent(),
            ChoiceMade(
                sceneId = "stranger",
                label = "报上姓名",
                target = "ending_a",
                alternatives = listOf(Alternative("沉默", "ending_b")),
                at = "t1",
            ),
        )
        val report = ReplayAnalyzer.buildReport(sampleStory(), events)
        val dp = report.decisionPoints.single()
        assertEquals(20, dp.sceneLine)
        assertEquals("", dp.sceneText)
    }

    @Test
    fun storyNullNoEnrichmentNoWarnings() {
        val events = listOf(
            startEvent(),
            SceneEnter(sceneId = "ghost", at = "t1"),
            ChoiceMade(
                sceneId = "ghost",
                label = "走",
                target = "somewhere",
                alternatives = listOf(Alternative("留", "here")),
                at = "t2",
            ),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        assertTrue(report.warnings.isEmpty())
        val dp = report.decisionPoints.single()
        assertEquals(-1, dp.sceneLine)
        assertEquals("", dp.sceneText)
    }

    @Test
    fun missingSceneProducesWarningButReportStillGenerated() {
        val events = listOf(
            startEvent(),
            SceneEnter(sceneId = "missing_scene", at = "t1"),
            ChoiceMade(
                sceneId = "another_missing",
                label = "走",
                target = "x",
                alternatives = listOf(Alternative("留", "y")),
                at = "t2",
            ),
        )
        val report = ReplayAnalyzer.buildReport(sampleStory(), events)
        assertEquals(2, report.warnings.size)
        assertTrue(report.warnings[0].contains("missing_scene"))
        assertTrue(report.warnings[1].contains("another_missing"))
        assertEquals(1, report.decisionPoints.size)
        assertEquals(-1, report.decisionPoints[0].sceneLine)
    }

    @Test
    fun voteRoundsGroupedByRoundAscending() {
        val events = listOf(
            startEvent(),
            VoteCast(voter = "a", target = "b", round = 2, at = "t1"),
            VoteCast(voter = "b", target = "a", round = 2, at = "t2"),
            Elimination(player = "b", reason = "票数最多", round = 2, at = "t3"),
            VoteCast(voter = "a", target = "c", round = 1, at = "t4"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        assertEquals(2, report.voteRounds.size)
        assertEquals(1, report.voteRounds[0].round)
        assertEquals(2, report.voteRounds[1].round)
        assertEquals(2, report.voteRounds[1].votes.size)
        assertNotNull(report.voteRounds[1].eliminated)
        assertEquals("b", report.voteRounds[1].eliminated!!.player)
        assertNull(report.voteRounds[0].eliminated)
    }

    @Test
    fun playerStatsSortedByVotesReceivedDesc() {
        val events = listOf(
            startEvent(),
            VoteCast(voter = "a", target = "b", round = 1, at = "t1"),
            VoteCast(voter = "c", target = "b", round = 1, at = "t2"),
            VoteCast(voter = "b", target = "c", round = 1, at = "t3"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        // b 被投 2 次，c 被投 1 次，a 被投 0 次
        assertEquals("b", report.playerStats[0].player)
        assertEquals(2, report.playerStats[0].votesReceived)
        assertEquals(1, report.playerStats[0].votesCast)
        assertEquals("c", report.playerStats[1].player)
        assertEquals(1, report.playerStats[1].votesReceived)
        assertEquals(1, report.playerStats[1].votesCast)
        assertEquals("a", report.playerStats[2].player)
        assertEquals(0, report.playerStats[2].votesReceived)
        assertEquals(1, report.playerStats[2].votesCast)
    }

    @Test
    fun playerStatsEliminationRoundRecorded() {
        val events = listOf(
            startEvent(),
            VoteCast(voter = "a", target = "b", round = 1, at = "t1"),
            Elimination(player = "b", reason = "票数最多", round = 1, at = "t2"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        val bStats = report.playerStats.first { it.player == "b" }
        assertEquals(1, bStats.eliminatedRound)
        val aStats = report.playerStats.first { it.player == "a" }
        assertNull(aStats.eliminatedRound)
    }

    @Test
    fun noSessionEndMeansNullEndFields() {
        val events = listOf(
            startEvent(),
            SceneEnter(sceneId = "prologue", at = "t1"),
        )
        val report = ReplayAnalyzer.buildReport(sampleStory(), events)
        assertNull(report.endedAt)
        assertNull(report.outcome)
        assertNull(report.winner)
    }

    @Test
    fun sessionEndFillsEndFields() {
        val events = listOf(
            startEvent(),
            SessionEnd(outcome = "胜利", winner = "a", at = "t9"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        assertEquals("t9", report.endedAt)
        assertEquals("胜利", report.outcome)
        assertEquals("a", report.winner)
    }

    @Test
    fun emptyEventsThrowsIllegalArgument() {
        assertFailsWith<IllegalArgumentException> {
            ReplayAnalyzer.buildReport(null, emptyList())
        }
    }

    @Test
    fun firstEventNotSessionStartThrows() {
        val events = listOf(
            SceneEnter(sceneId = "prologue", at = "t1"),
        )
        assertFailsWith<IllegalArgumentException> {
            ReplayAnalyzer.buildReport(null, events)
        }
    }

    @Test
    fun keyMomentsCollected() {
        val events = listOf(
            startEvent(),
            KeyMoment(note = "关键抉择", sceneId = "hall", at = "t1"),
            KeyMoment(note = "全局标注", sceneId = null, at = "t2"),
        )
        val report = ReplayAnalyzer.buildReport(sampleStory(), events)
        assertEquals(2, report.keyMoments.size)
        assertEquals("关键抉择", report.keyMoments[0].note)
        assertEquals("hall", report.keyMoments[0].sceneId)
        assertNull(report.keyMoments[1].sceneId)
    }

    @Test
    fun timelinePreservesOriginalOrder() {
        val events = listOf(
            startEvent(),
            SceneEnter(sceneId = "prologue", at = "t1"),
            KeyMoment(note = "n", sceneId = null, at = "t2"),
            SceneEnter(sceneId = "hall", at = "t3"),
            SessionEnd(outcome = "结束", winner = null, at = "t4"),
        )
        val report = ReplayAnalyzer.buildReport(sampleStory(), events)
        assertEquals(events, report.timeline)
    }

    @Test
    fun sessionMetaTakenFromFirstEvent() {
        val events = listOf(
            SessionStart(sessionId = "abc", scriptFile = "z.interlude", playerCount = 3, at = "t0"),
            SessionEnd(outcome = "x", winner = null, at = "t1"),
        )
        val report = ReplayAnalyzer.buildReport(null, events)
        assertEquals("abc", report.sessionId)
        assertEquals("z.interlude", report.scriptFile)
        assertEquals("t0", report.startedAt)
    }
}
