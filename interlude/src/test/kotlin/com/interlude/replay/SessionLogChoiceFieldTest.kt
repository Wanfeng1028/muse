package com.interlude.replay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SessionLogChoiceFieldTest {

    private val sessionPrefix = "{\"session\": {\"id\":\"t1\",\"script\":\"s\",\"startedAt\":\"t\"},\"events\": ["

    private fun wrap(eventJson: String): String = sessionPrefix + eventJson + "]}"

    @Test
    fun choiceMissingLabel() {
        val text = wrap("{\"type\":\"choice\",\"scene\":\"a\",\"target\":\"b\",\"at\":\"t\"}")
        val ex = kotlin.runCatching { SessionLog.parse(text) }.exceptionOrNull()
        assertTrue(ex is SessionLogParseException, "缺少 label 的 choice 事件应抛 SessionLogParseException")
        assertTrue(
            ex.message!!.contains("events[0].label"),
            "异常信息应包含 events[0].label，实际为：${ex.message}"
        )
    }

    @Test
    fun choiceLabelNotString() {
        val text = wrap("{\"type\":\"choice\",\"scene\":\"a\",\"label\":42,\"target\":\"b\",\"at\":\"t\"}")
        val ex = kotlin.runCatching { SessionLog.parse(text) }.exceptionOrNull()
        assertTrue(ex is SessionLogParseException, "label 为非 string 的 choice 事件应抛 SessionLogParseException")
        assertTrue(
            ex.message!!.contains("label 必须是 string"),
            "异常信息应包含 label 必须是 string，实际为：${ex.message}"
        )
    }

    @Test
    fun sceneMissingScene() {
        val text = wrap("{\"type\":\"scene\",\"at\":\"t\"}")
        val ex = kotlin.runCatching { SessionLog.parse(text) }.exceptionOrNull()
        assertTrue(ex is SessionLogParseException, "缺少 scene 的 scene 事件应抛 SessionLogParseException")
        assertTrue(
            ex.message!!.contains("events[0].scene"),
            "异常信息应包含 events[0].scene，实际为：${ex.message}"
        )
    }

    @Test
    fun sceneEventParsed() {
        val text = wrap("{\"type\":\"scene\",\"scene\":\"hall\",\"at\":\"2026-10-16T20:00:05+08:00\"}")
        val events = SessionLog.parse(text)
        assertEquals(2, events.size, "应解析出 SessionStart 与 SceneEnter 两个事件")
        assertTrue(events[0] is SessionStart, "第 0 个事件应为 SessionStart")
        val scene = events[1]
        assertTrue(scene is SceneEnter, "第 1 个事件应为 SceneEnter")
        assertEquals("hall", (scene as SceneEnter).sceneId, "sceneId 应为 hall")
        assertEquals("2026-10-16T20:00:05+08:00", scene.at, "at 字段应原样保留")
    }

    @Test
    fun noteOptionalSceneNull() {
        val text = wrap("{\"type\":\"note\",\"note\":\"关键\",\"scene\":null,\"at\":\"t\"}")
        val events = SessionLog.parse(text)
        assertEquals(2, events.size, "应解析出 SessionStart 与 KeyMoment 两个事件")
        val moment = events[1]
        assertTrue(moment is KeyMoment, "第 1 个事件应为 KeyMoment")
        assertEquals(null, (moment as KeyMoment).sceneId, "显式 null 的 scene 应解析为 null")
        assertEquals("关键", moment.note, "note 字段应解析为关键")
    }
}