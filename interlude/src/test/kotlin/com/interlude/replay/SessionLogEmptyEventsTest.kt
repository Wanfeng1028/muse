package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith

class SessionLogEmptyEventsTest {

    private val emptyEventsJson =
        "{\"session\": {\"id\":\"t1\",\"script\":\"s.interlude\",\"players\":2,\"startedAt\":\"2026-10-16T20:00:00+08:00\"},\"events\": []}"

    private val emptyEventsNoPlayersJson =
        "{\"session\": {\"id\":\"t1\",\"script\":\"s.interlude\",\"startedAt\":\"2026-10-16T20:00:00+08:00\"},\"events\": []}"

    @Test
    fun emptyEventsOnlySessionStart() {
        val events = SessionLog.parse(emptyEventsJson)
        assertEquals(1, events.size, "events 为空数组时应只合成 SessionStart 一个元素")
        val first = events[0]
        assertTrue(first is SessionStart, "第 0 个元素必须是 SessionStart")
        val start = first as SessionStart
        assertEquals("t1", start.sessionId, "sessionId 应取自 session.id")
        assertEquals("s.interlude", start.scriptFile, "scriptFile 应取自 session.script")
        assertEquals(2, start.playerCount, "playerCount 应取自 session.players")
        assertEquals("2026-10-16T20:00:00+08:00", start.at, "at 应取自 session.startedAt")
    }

    @Test
    fun emptyEventsDefaultPlayers() {
        val events = SessionLog.parse(emptyEventsNoPlayersJson)
        assertEquals(1, events.size, "events 为空数组时应只合成 SessionStart 一个元素")
        val start = events[0]
        assertTrue(start is SessionStart, "第 0 个元素必须是 SessionStart")
        assertEquals(1, (start as SessionStart).playerCount, "session 缺省 players 时 playerCount 应为 1")
    }

    @Test
    fun buildReportWithOnlyStart() {
        val events = SessionLog.parse(emptyEventsJson)
        assertEquals(1, events.size, "解析结果应只含 SessionStart")
        val report = ReplayAnalyzer.buildReport(null, events)
        val rendered = ReplayMarkdown.render(report)
        assertTrue(rendered.contains("对局开始"), "时间线应渲染出 SessionStart 条目")
        assertTrue(rendered.contains("事件总数：1"), "事件总数应为 1")
        assertFalse(rendered.contains("本局无事件记录。"), "经 buildReport 产出的 timeline 恒非空，不应出现空时间线降级文案")
        assertTrue(rendered.contains("本局没有记录到抉择点。"), "无抉择点时应输出对应提示")
        assertTrue(rendered.contains("本局无投票记录。"), "无投票时应输出对应提示")
        assertTrue(rendered.contains("无。"), "关键标注节无内容时应输出 无。")
        assertTrue(rendered.contains("未记录"), "结束时间或对局结果缺失时应输出 未记录")
        assertFalse(rendered.contains("## 数据问题"), "无警告时不应输出数据问题节")
    }
}