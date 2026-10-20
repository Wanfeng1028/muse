package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class SessionLogUnknownTypeTest {

    private val sessionPart = "{\"id\":\"t1\",\"script\":\"s\",\"startedAt\":\"2026-10-16T20:00:00+08:00\"}"

    private fun buildLog(eventsJson: String): String =
        "{\"session\":$sessionPart,\"events\":$eventsJson}"

    @Test
    fun unknownTypeThrowsWithIndexAndTypeName() {
        val text = buildLog("[{\"type\":\"dance\",\"at\":\"2026-10-16T20:00:05+08:00\"}]")
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(text)
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("未知的事件 type"), "message 应包含未知事件 type 提示，实际为：$msg")
        assertTrue(msg.contains("dance"), "message 应包含未知 type 名称 dance，实际为：$msg")
        assertTrue(msg.contains("events[0]"), "message 应包含事件序号 events[0]，实际为：$msg")
    }

    @Test
    fun unknownTypeSecondIndexReportsSecondIndex() {
        val text = buildLog(
            "[{\"type\":\"scene\",\"scene\":\"a\",\"at\":\"t1\"},{\"type\":\"warp\",\"at\":\"t2\"}]"
        )
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(text)
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("events[1]"), "message 应包含第二个事件的序号 events[1]，实际为：$msg")
        assertTrue(msg.contains("warp"), "message 应包含未知 type 名称 warp，实际为：$msg")
    }

    @Test
    fun eventNotObjectReportsMustBeObject() {
        val text = buildLog("[\"oops\"]")
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(text)
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("events[0]"), "message 应包含事件序号 events[0]，实际为：$msg")
        assertTrue(msg.contains("必须是 object"), "message 应提示事件必须是 object，实际为：$msg")
    }

    @Test
    fun missingTypeFieldReportsMissingType() {
        val text = buildLog("[{\"scene\":\"a\",\"at\":\"t\"}]")
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(text)
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("缺少必需字段 type"), "message 应提示缺少必需字段 type，实际为：$msg")
        assertTrue(msg.contains("events[0]"), "message 应包含事件序号 events[0]，实际为：$msg")
    }

    @Test
    fun typeNotStringReportsTypeMustBeString() {
        val text = buildLog("[{\"type\":42,\"at\":\"t\"}]")
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(text)
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("type 必须是 string"), "message 应提示 type 必须是 string，实际为：$msg")
        assertTrue(msg.contains("events[0]"), "message 应包含事件序号 events[0]，实际为：$msg")
        assertFalse(msg.contains("未知的事件 type"), "type 非 string 时不应走未知 type 分支，实际为：$msg")
    }
}