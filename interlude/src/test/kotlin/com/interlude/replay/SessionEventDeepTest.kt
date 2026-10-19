package com.interlude.replay

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*

class SessionEventDeepTest {

    // 事实来源：SessionEvent.kt 第 5 行 `sealed interface SessionEvent { val at: String }`，所有事件均实现该接口并透传 at。
    @Test
    fun allSevenEventsImplementSessionEventAndPassThroughAt() {
        val events: List<SessionEvent> = listOf(
            SessionStart("sid", "script.rpy", 4, "t1"),
            SceneEnter("scene1", "t2"),
            ChoiceMade("scene1", "label", "target", emptyList(), "t3"),
            VoteCast("voter", "target", 1, "t4"),
            Elimination("player", "reason", 1, "t5"),
            KeyMoment("note", "scene1", "t6"),
            SessionEnd("outcome", "winner", "t7"),
        )
        assertEquals(7, events.size)
        for (e in events) {
            assertTrue(e is SessionEvent)
        }
        assertEquals("t1", events[0].at)
        assertEquals("t2", events[1].at)
        assertEquals("t3", events[2].at)
        assertEquals("t4", events[3].at)
        assertEquals("t5", events[4].at)
        assertEquals("t6", events[5].at)
        assertEquals("t7", events[6].at)
    }

    // 事实来源：SessionEvent.kt 第 9-14 行 `data class SessionStart(sessionId, scriptFile, playerCount, at)`。
    @Test
    fun sessionStartFieldsAreAccessible() {
        val start = SessionStart("s-1", "story.rpy", 5, "2026-10-16T20:00:00+08:00")
        assertEquals("s-1", start.sessionId)
        assertEquals("story.rpy", start.scriptFile)
        assertEquals(5, start.playerCount)
        assertEquals("2026-10-16T20:00:00+08:00", start.at)
    }

    // 事实来源：SessionEvent.kt 第 18-23 行 `ChoiceMade.alternatives: List<Alternative>`，允许为空列表。
    @Test
    fun choiceMadeWithEmptyAlternativesIsValid() {
        val choice = ChoiceMade("scene1", "go", "target1", emptyList(), "t")
        assertTrue(choice.alternatives.isEmpty())
        assertEquals(0, choice.alternatives.size)
        assertEquals("scene1", choice.sceneId)
        assertEquals("go", choice.label)
        assertEquals("target1", choice.target)
    }

    // 事实来源：SessionEvent.kt 第 3 行 `data class Alternative(val label: String, val target: String)`，data class 提供结构相等。
    @Test
    fun alternativeEqualityIsStructural() {
        val a = Alternative("a", "t1")
        val b = Alternative("a", "t1")
        val c = Alternative("a", "t2")
        assertEquals(a, b)
        assertEquals(a.hashCode(), b.hashCode())
        assertNotEquals(a, c)
    }

    // 事实来源：SessionEvent.kt 第 27 行 `data class KeyMoment(note, sceneId: String?, at)`，sceneId 可为 null。
    @Test
    fun keyMomentSceneIdCanBeNull() {
        val moment = KeyMoment("note", null, "t")
        assertNull(moment.sceneId)
        assertEquals("note", moment.note)
        assertEquals("t", moment.at)
    }

    // 事实来源：SessionEvent.kt 第 31 行 `data class SessionEnd(outcome, winner: String?, at)`，winner 可为 null。
    @Test
    fun sessionEndWinnerCanBeNull() {
        val end = SessionEnd("draw", null, "t")
        assertNull(end.winner)
        assertEquals("draw", end.outcome)
        assertEquals("t", end.at)
    }

    // 事实来源：SessionEvent.kt 第 25、29 行 VoteCast/Elimination 的 `round: Int` 原样保留。
    @Test
    fun voteCastAndEliminationRoundIsPreserved() {
        val vote0 = VoteCast("voter", "target", 0, "t")
        val vote3 = VoteCast("voter", "target", 3, "t")
        assertEquals(0, vote0.round)
        assertEquals(3, vote3.round)

        val elim0 = Elimination("player", "reason", 0, "t")
        val elim3 = Elimination("player", "reason", 3, "t")
        assertEquals(0, elim0.round)
        assertEquals(3, elim3.round)
    }

    // 事实来源：SessionEvent.kt 第 16 行 `data class SceneEnter(sceneId, at)`，data class copy 可改 sceneId。
    @Test
    fun sceneEnterCopyChangesSceneId() {
        val original = SceneEnter("s1", "t")
        val copied = original.copy(sceneId = "s2")
        assertEquals("s2", copied.sceneId)
        assertEquals("s1", original.sceneId)
        assertEquals("t", copied.at)
    }

    // 事实来源：SessionEvent.kt 第 5 行 sealed interface，多态列表可混合不同类型并通过 is 区分。
    @Test
    fun mixedEventListKeepsPolymorphism() {
        val start = SessionStart("s", "f", 2, "t1")
        val enter = SceneEnter("scene1", "t2")
        val list: List<SessionEvent> = listOf(start, enter)
        assertEquals(2, list.size)
        assertTrue(list[0] is SessionStart)
        assertTrue(list[1] is SceneEnter)
        assertFalse(list[0] is SceneEnter)
        when (val e = list[1]) {
            is SceneEnter -> assertEquals("scene1", e.sceneId)
            else -> fail("expected SceneEnter")
        }
    }

    // 事实来源：SessionEvent.kt 第 5 行 `val at: String`，模块不对时间戳做解析，字符串原样保留。
    @Test
    fun timestampStringIsPassedThroughVerbatim() {
        val ts = "2026-10-16T20:01:00+08:00"
        val events: List<SessionEvent> = listOf(
            SessionStart("s", "f", 1, ts),
            SceneEnter("scene1", ts),
            ChoiceMade("scene1", "l", "t", emptyList(), ts),
            VoteCast("v", "t", 1, ts),
            Elimination("p", "r", 1, ts),
            KeyMoment("n", null, ts),
            SessionEnd("o", null, ts),
        )
        for (e in events) {
            assertEquals(ts, e.at)
        }
        assertEquals(ts, SessionStart("s", "f", 1, ts).at)
    }
}
