package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SessionLogAlternativesTest {

    private val sessionPrefix = """{"session":{"id":"t1","script":"s","startedAt":"t"},"events":["""

    private fun buildLog(event: String): String = sessionPrefix + event + "]}"

    @Test
    fun missingAlternativesEmptyList() {
        val text = buildLog(
            """{"type":"choice","scene":"a","label":"走","target":"b","at":"t"}"""
        )
        val events = SessionLog.parse(text)
        assertEquals(2, events.size, "事件数应为 SessionStart 加一个 choice 事件")
        val choice = events[1]
        assertTrue(choice is ChoiceMade, "第二个事件应为 ChoiceMade")
        choice as ChoiceMade
        assertEquals("a", choice.sceneId, "choice 的 scene 应解析为 a")
        assertEquals("走", choice.label, "choice 的 label 应解析为 走")
        assertEquals("b", choice.target, "choice 的 target 应解析为 b")
        assertTrue(choice.alternatives.isEmpty(), "缺省 alternatives 应为空列表")
    }

    @Test
    fun alternativesParsed() {
        val text = buildLog(
            """{"type":"choice","scene":"a","label":"走","target":"b","alternatives":[{"label":"留","target":"c"},{"label":"跑","target":"d"}],"at":"t"}"""
        )
        val events = SessionLog.parse(text)
        val choice = events[1] as ChoiceMade
        assertEquals(2, choice.alternatives.size, "alternatives 应解析出 2 个元素")
        assertEquals("留", choice.alternatives[0].label, "第 0 个 alternative 的 label 应为 留")
        assertEquals("c", choice.alternatives[0].target, "第 0 个 alternative 的 target 应为 c")
        assertEquals("跑", choice.alternatives[1].label, "第 1 个 alternative 的 label 应为 跑")
        assertEquals("d", choice.alternatives[1].target, "第 1 个 alternative 的 target 应为 d")
    }

    @Test
    fun alternativesNotArray() {
        val text = buildLog(
            """{"type":"choice","scene":"a","label":"走","target":"b","alternatives":"nope","at":"t"}"""
        )
        val ex = kotlin.runCatching { SessionLog.parse(text) }.exceptionOrNull()
        assertTrue(ex is SessionLogParseException, "非数组 alternatives 应抛 SessionLogParseException")
        val message = ex.message ?: ""
        assertTrue(message.contains("alternatives 必须是 array"), "异常信息应包含 alternatives 必须是 array，实际为 $message")
        assertTrue(message.contains("events[0]"), "异常信息应包含 events[0]，实际为 $message")
    }

    @Test
    fun alternativeItemNotObject() {
        val text = buildLog(
            """{"type":"choice","scene":"a","label":"走","target":"b","alternatives":["x"],"at":"t"}"""
        )
        val ex = kotlin.runCatching { SessionLog.parse(text) }.exceptionOrNull()
        assertTrue(ex is SessionLogParseException, "元素非 object 应抛 SessionLogParseException")
        val message = ex.message ?: ""
        assertTrue(message.contains("alternatives[0]"), "异常信息应包含 alternatives[0]，实际为 $message")
        assertTrue(message.contains("必须是 object"), "异常信息应包含 必须是 object，实际为 $message")
    }

    @Test
    fun alternativeMissingLabel() {
        val text = buildLog(
            """{"type":"choice","scene":"a","label":"走","target":"b","alternatives":[{"target":"c"}],"at":"t"}"""
        )
        val ex = kotlin.runCatching { SessionLog.parse(text) }.exceptionOrNull()
        assertTrue(ex is SessionLogParseException, "缺少 label 应抛 SessionLogParseException")
        val message = ex.message ?: ""
        assertTrue(message.contains("alternatives[0].label"), "异常信息应包含 alternatives[0].label，实际为 $message")
    }
}