package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

class SessionLogMissingTopFieldsTest {

    @Test
    fun missingSessionField() {
        val json = """{"events": []}"""
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(json)
        }
        assertTrue(
            ex.message!!.contains("缺少顶层字段 session"),
            "缺少 session 字段时错误信息应包含 '缺少顶层字段 session'，实际为：${ex.message}"
        )
    }

    @Test
    fun missingEventsField() {
        val json = """{"session": {"id":"t1","script":"s","startedAt":"2026-10-16T20:00:00+08:00"}}"""
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(json)
        }
        assertTrue(
            ex.message!!.contains("缺少顶层字段 events"),
            "缺少 events 字段时错误信息应包含 '缺少顶层字段 events'，实际为：${ex.message}"
        )
    }

    @Test
    fun sessionNotObject() {
        val json = """{"session": "oops","events": []}"""
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(json)
        }
        assertTrue(
            ex.message!!.contains("session 必须是 object"),
            "session 非 object 时错误信息应包含 'session 必须是 object'，实际为：${ex.message}"
        )
        assertTrue(
            ex.message!!.contains("string"),
            "session 为字符串时错误信息应包含实际类型 'string'，实际为：${ex.message}"
        )
    }

    @Test
    fun eventsNotArray() {
        val json = """{"session": {"id":"t1","script":"s","startedAt":"t"},"events": {}}"""
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(json)
        }
        assertTrue(
            ex.message!!.contains("events 必须是 array"),
            "events 非 array 时错误信息应包含 'events 必须是 array'，实际为：${ex.message}"
        )
        assertTrue(
            ex.message!!.contains("object"),
            "events 为对象时错误信息应包含实际类型 'object'，实际为：${ex.message}"
        )
    }

    @Test
    fun topLevelNotObject() {
        val json = """[1,2,3]"""
        val ex = assertFailsWith<SessionLogParseException> {
            SessionLog.parse(json)
        }
        assertTrue(
            ex.message!!.contains("顶层必须是 object"),
            "顶层非 object 时错误信息应包含 '顶层必须是 object'，实际为：${ex.message}"
        )
        assertTrue(
            ex.message!!.contains("array"),
            "顶层为数组时错误信息应包含实际类型 'array'，实际为：${ex.message}"
        )
    }
}