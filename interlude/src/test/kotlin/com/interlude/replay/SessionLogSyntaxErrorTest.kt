package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

class SessionLogSyntaxErrorTest {

    @Test
    fun emptyInput() {
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse("")
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("JSON"), "空输入异常消息应包含 JSON，实际为：$msg")
        assertTrue(msg.contains("输入为空"), "空输入异常消息应包含 输入为空，实际为：$msg")
    }

    @Test
    fun unclosedString() {
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse("{\"session\": {\"id\":\"t1\"")
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("JSON"), "字符串未闭合异常消息应包含 JSON，实际为：$msg")
    }

    @Test
    fun trailingGarbage() {
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse("{\"session\": {\"id\":\"t1\",\"script\":\"s\",\"startedAt\":\"t\"},\"events\": []} xyz")
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("JSON 结尾存在多余字符"), "多余字符异常消息应包含 JSON 结尾存在多余字符，实际为：$msg")
    }

    @Test
    fun illegalChar() {
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse("{\"a\":!}")
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("JSON"), "非法字符异常消息应包含 JSON，实际为：$msg")
        assertTrue(msg.contains("非法字符"), "非法字符异常消息应包含 非法字符，实际为：$msg")
    }

    @Test
    fun missingSessionId() {
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse("{\"session\": {\"script\":\"s\",\"startedAt\":\"t\"},\"events\": []}")
        }
        val msg = ex.message ?: ""
        assertTrue(msg.contains("session.id"), "缺少 session.id 异常消息应包含 session.id，实际为：$msg")
        assertTrue(msg.contains("缺少必需字段"), "缺少 session.id 异常消息应包含 缺少必需字段，实际为：$msg")
    }
}