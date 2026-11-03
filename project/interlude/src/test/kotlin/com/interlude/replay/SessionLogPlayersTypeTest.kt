package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class SessionLogPlayersTypeTest {

    @Test
    fun playersDoubleRejected() {
        val text = """
            {"session":{"id":"t1","script":"s","startedAt":"t","players":1.5},"events":[]}
        """.trimIndent()
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(text)
        }
        assertTrue(
            ex.message!!.contains("session.players 必须是 int"),
            "players 为 double 时应报字段 session.players 必须是 int，实际为：${ex.message}"
        )
    }

    @Test
    fun playersStringRejected() {
        val text = """
            {"session":{"id":"t1","script":"s","startedAt":"t","players":"two"},"events":[]}
        """.trimIndent()
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(text)
        }
        assertTrue(
            ex.message!!.contains("session.players 必须是 int"),
            "players 为 string 时应报字段 session.players 必须是 int，实际为：${ex.message}"
        )
    }

    @Test
    fun playersIntAccepted() {
        val text = """
            {"session":{"id":"t1","script":"s","startedAt":"t","players":4},"events":[]}
        """.trimIndent()
        val events = SessionLog.parse(text)
        assertEquals(1, events.size, "仅含 session 合成事件时 events 列表长度应为 1")
        val start = events[0]
        assertTrue(start is SessionStart, "首元素应为 SessionStart")
        assertEquals(4, (start as SessionStart).playerCount, "players 为 4 时 playerCount 应为 4")
    }

    @Test
    fun playersNullRejected() {
        val text = """
            {"session":{"id":"t1","script":"s","startedAt":"t","players":null},"events":[]}
        """.trimIndent()
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(text)
        }
        assertTrue(
            ex.message!!.contains("session.players 必须是 int"),
            "显式 null 不等于缺省，应报字段 session.players 必须是 int，实际为：${ex.message}"
        )
    }
}