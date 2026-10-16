package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class SessionLogTest {

    /** 完整日志：7 种事件（SessionStart + 6 种 events 类型）齐全。 */
    private val fullLog = """
        {
          "session": { "id": "s1", "script": "sample.interlude", "players": 1, "startedAt": "2026-10-16T20:00:00+08:00" },
          "events": [
            { "type": "scene", "scene": "prologue", "at": "2026-10-16T20:00:05+08:00" },
            { "type": "choice", "scene": "hall", "label": "和陌生人搭话", "target": "stranger",
              "alternatives": [ { "label": "推门离开", "target": "exit" } ], "at": "2026-10-16T20:01:00+08:00" },
            { "type": "vote", "voter": "A", "target": "B", "round": 1, "at": "2026-10-16T20:02:00+08:00" },
            { "type": "elimination", "player": "B", "reason": "票数最高", "round": 1, "at": "2026-10-16T20:03:00+08:00" },
            { "type": "note", "note": "关键抉择点", "scene": "hall", "at": "2026-10-16T20:04:00+08:00" },
            { "type": "end", "outcome": "抵达 ending_a", "winner": null, "at": "2026-10-16T20:05:00+08:00" }
          ]
        }
    """.trimIndent()

    @Test
    fun `完整日志解析_首元素为 SessionStart 且字段正确`() {
        val events = SessionLog.parse(fullLog)
        assertEquals(7, events.size)

        val start = assertIs<SessionStart>(events[0])
        assertEquals("s1", start.sessionId)
        assertEquals("sample.interlude", start.scriptFile)
        assertEquals(1, start.playerCount)
        assertEquals("2026-10-16T20:00:00+08:00", start.at)
    }

    @Test
    fun `完整日志解析_ChoiceMade 与 alternatives 内容正确`() {
        val events = SessionLog.parse(fullLog)
        val choice = assertIs<ChoiceMade>(events[2])
        assertEquals("hall", choice.sceneId)
        assertEquals("和陌生人搭话", choice.label)
        assertEquals("stranger", choice.target)
        assertEquals(listOf(Alternative("推门离开", "exit")), choice.alternatives)
        assertEquals("2026-10-16T20:01:00+08:00", choice.at)
    }

    @Test
    fun `完整日志解析_KeyMoment sceneId 可为 null 且 SessionEnd winner 可为 null`() {
        val events = SessionLog.parse(fullLog)
        val note = assertIs<KeyMoment>(events[5])
        assertEquals("关键抉择点", note.note)
        assertEquals("hall", note.sceneId)

        val end = assertIs<SessionEnd>(events[6])
        assertEquals("抵达 ending_a", end.outcome)
        assertNull(end.winner)
    }

    @Test
    fun `完整日志解析_各事件类型顺序与具体类型正确`() {
        val events = SessionLog.parse(fullLog)
        assertIs<SessionStart>(events[0])
        assertIs<SceneEnter>(events[1])
        assertIs<ChoiceMade>(events[2])
        assertIs<VoteCast>(events[3])
        assertIs<Elimination>(events[4])
        assertIs<KeyMoment>(events[5])
        assertIs<SessionEnd>(events[6])
    }

    @Test
    fun `空 events 数组_返回只含 SessionStart 的列表`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "2026-10-16T20:00:00+08:00" }, "events": [] }
        """.trimIndent()
        val events = SessionLog.parse(text)
        assertEquals(1, events.size)
        assertIs<SessionStart>(events[0])
    }

    @Test
    fun `未知 type_抛异常且 message 含事件序号与该 type`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" },
              "events": [ { "type": "dance", "at": "t1" } ] }
        """.trimIndent()
        val ex = assertFailsWith<SessionLogParseException> { SessionLog.parse(text) }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("events[0]"), "message 应含事件序号，实际：$msg")
        assertTrue(msg.contains("dance"), "message 应含未知 type，实际：$msg")
    }

    @Test
    fun `choice 缺 target_抛异常且 message 含事件序号与字段名`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" },
              "events": [ { "type": "choice", "scene": "hall", "label": "走", "at": "t1" } ] }
        """.trimIndent()
        val ex = assertFailsWith<SessionLogParseException> { SessionLog.parse(text) }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("events[0]"), "message 应含事件序号，实际：$msg")
        assertTrue(msg.contains("target"), "message 应含字段名 target，实际：$msg")
    }

    @Test
    fun `缺顶层 session_抛异常`() {
        val text = """{ "events": [] }"""
        val ex = assertFailsWith<SessionLogParseException> { SessionLog.parse(text) }
        assertTrue((ex.message ?: "").contains("session"))
    }

    @Test
    fun `缺顶层 events_抛异常`() {
        val text = """{ "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" } }"""
        val ex = assertFailsWith<SessionLogParseException> { SessionLog.parse(text) }
        assertTrue((ex.message ?: "").contains("events"))
    }

    @Test
    fun `JSON 语法错误_缺右括号_抛异常且 message 含 JSON`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" },
              "events": [ { "type": "scene", "scene": "p", "at": "t1" }
        """.trimIndent()
        val ex = assertFailsWith<SessionLogParseException> { SessionLog.parse(text) }
        assertTrue((ex.message ?: "").contains("JSON"), "message 应含 JSON 字样")
    }

    @Test
    fun `alternatives 缺省_为空列表`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" },
              "events": [ { "type": "choice", "scene": "hall", "label": "走", "target": "exit", "at": "t1" } ] }
        """.trimIndent()
        val events = SessionLog.parse(text)
        val choice = assertIs<ChoiceMade>(events[1])
        assertEquals(emptyList(), choice.alternatives)
    }

    @Test
    fun `session players 缺省_为 1`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" }, "events": [] }
        """.trimIndent()
        val start = assertIs<SessionStart>(SessionLog.parse(text)[0])
        assertEquals(1, start.playerCount)
    }

    @Test
    fun `字段类型错误 round 写成字符串_抛异常`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" },
              "events": [ { "type": "vote", "voter": "A", "target": "B", "round": "一", "at": "t1" } ] }
        """.trimIndent()
        val ex = assertFailsWith<SessionLogParseException> { SessionLog.parse(text) }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("events[0]"), "message 应含事件序号，实际：$msg")
        assertTrue(msg.contains("round"), "message 应含字段名 round，实际：$msg")
    }

    @Test
    fun `转义字符串_双引号与 unicode 转义正确解析`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" },
              "events": [ { "type": "note", "note": "她说：\"中\u4e2d\"", "at": "t1" } ] }
        """.trimIndent()
        val events = SessionLog.parse(text)
        val note = assertIs<KeyMoment>(events[1])
        assertEquals("她说：\"中中\"", note.note)
    }

    @Test
    fun `vote 与 elimination 的 round 正确解析为 Int`() {
        val events = SessionLog.parse(fullLog)
        val vote = assertIs<VoteCast>(events[3])
        assertEquals(1, vote.round)
        assertEquals("A", vote.voter)
        assertEquals("B", vote.target)

        val elim = assertIs<Elimination>(events[4])
        assertEquals(1, elim.round)
        assertEquals("B", elim.player)
        assertEquals("票数最高", elim.reason)
    }

    @Test
    fun `events 不是数组_抛异常`() {
        val text = """
            { "session": { "id": "s1", "script": "a.interlude", "startedAt": "t" }, "events": {} }
        """.trimIndent()
        val ex = assertFailsWith<SessionLogParseException> { SessionLog.parse(text) }
        assertTrue((ex.message ?: "").contains("events"))
    }
}
