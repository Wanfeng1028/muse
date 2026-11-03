package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

class SessionLogRoundTypeTest {

    private fun voteLog(roundJson: String): String =
        "{\"session\":{\"id\":\"t1\",\"script\":\"s\",\"startedAt\":\"t\"}," +
            "\"events\":[{\"type\":\"vote\",\"voter\":\"a\",\"target\":\"b\",\"round\":$roundJson,\"at\":\"t\"}]}"

    private fun eliminationLog(roundPart: String): String =
        "{\"session\":{\"id\":\"t1\",\"script\":\"s\",\"startedAt\":\"t\"}," +
            "\"events\":[{\"type\":\"elimination\",\"player\":\"a\",\"reason\":\"票出\"$roundPart,\"at\":\"t\"}]}"

    @Test
    fun voteRoundStringRejected() {
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(voteLog("\"1\""))
        }
        val message = ex.message ?: ""
        assertTrue(message.contains("round 必须是 int"), "vote 的 round 为字符串时应报字段 round 必须是 int，实际为：$message")
        assertTrue(message.contains("events[0]"), "错误信息应携带事件序号 events[0]，实际为：$message")
    }

    @Test
    fun voteRoundDoubleRejected() {
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(voteLog("1.0"))
        }
        val message = ex.message ?: ""
        assertTrue(message.contains("必须是 int"), "vote 的 round 为 1.0 时因是 double 应报必须是 int，实际为：$message")
    }

    @Test
    fun voteRoundIntAccepted() {
        val events = SessionLog.parse(voteLog("2"))
        assertEquals(2, events.size, "解析结果应含 SessionStart 与一个 vote 事件")
        val vote = events[1]
        assertTrue(vote is VoteCast, "第二个事件应为 VoteCast")
        assertEquals(2, (vote as VoteCast).round, "VoteCast.round 应解析为 2")
    }

    @Test
    fun eliminationMissingRound() {
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(eliminationLog(""))
        }
        val message = ex.message ?: ""
        assertTrue(message.contains("round"), "缺少 round 时错误信息应提及 round，实际为：$message")
        assertTrue(message.contains("缺少必需字段"), "缺少 round 时应报缺少必需字段，实际为：$message")
    }

    @Test
    fun eliminationRoundIntAccepted() {
        val events = SessionLog.parse(eliminationLog(",\"round\":3"))
        assertEquals(2, events.size, "解析结果应含 SessionStart 与一个 elimination 事件")
        val elimination = events[1]
        assertTrue(elimination is Elimination, "第二个事件应为 Elimination")
        assertEquals(3, (elimination as Elimination).round, "Elimination.round 应解析为 3")
    }
}