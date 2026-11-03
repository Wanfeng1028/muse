package dev.stagecue.shared.model

import dev.stagecue.shared.protocol.WsJson
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ModelDeepTest {

    @Test
    fun cueRoundTripAllFields() {
        val cue = Cue(
            id = "c1",
            name = "全字段",
            type = CueType.LIGHT,
            payload = "{\"color\":\"red\"}",
            durationMs = 5000,
            fadeInMs = 100,
            fadeOutMs = 200,
            fallbackCueId = "fb1",
            notes = "n",
            state = CueState.IDLE,
            order = 3
        )
        val json = WsJson.json.encodeToString(Cue.serializer(), cue)
        val decoded = WsJson.json.decodeFromString(Cue.serializer(), json)
        assertEquals(cue, decoded)
    }

    @Test
    fun cueDefaults() {
        val cue = Cue("c1", "开场", CueType.AUDIO)
        assertEquals("", cue.payload)
        assertEquals(0L, cue.durationMs)
        assertEquals(0L, cue.fadeInMs)
        assertEquals(0L, cue.fadeOutMs)
        assertNull(cue.fallbackCueId)
        assertEquals("", cue.notes)
        assertEquals(CueState.IDLE, cue.state)
        assertEquals(0, cue.order)
    }

    @Test
    fun cueTypeAllValuesRoundTrip() {
        val values = listOf(CueType.AUDIO, CueType.LIGHT, CueType.SUBTITLE, CueType.PROMPT)
        for (value in values) {
            val json = WsJson.json.encodeToString(CueType.serializer(), value)
            val decoded = WsJson.json.decodeFromString(CueType.serializer(), json)
            assertEquals(value, decoded)
        }
    }

    @Test
    fun showRoundTripEmptyCues() {
        val show = Show("s1", "演出", emptyList(), 1000L, 2000L)
        val json = WsJson.json.encodeToString(Show.serializer(), show)
        val decoded = WsJson.json.decodeFromString(Show.serializer(), json)
        assertEquals(show, decoded)
        assertTrue(decoded.cues.isEmpty())
    }

    @Test
    fun showRoundTripNestedCues() {
        val second = Cue("c2", "第二", CueType.SUBTITLE, order = 2)
        val first = Cue("c1", "第一", CueType.AUDIO, order = 1)
        val show = Show("s1", "演出", listOf(second, first), 1000L, 2000L)
        val json = WsJson.json.encodeToString(Show.serializer(), show)
        val decoded = WsJson.json.decodeFromString(Show.serializer(), json)
        assertEquals(show, decoded)
        assertEquals(2, decoded.cues.size)
        assertEquals(2, decoded.cues[0].order)
        assertEquals(1, decoded.cues[1].order)
        assertEquals("c2", decoded.cues[0].id)
        assertEquals("c1", decoded.cues[1].id)
    }

    @Test
    fun monitorStateAllNulls() {
        // 推导（实测修正）：WsJson 使用 explicitNulls = false，编码时会省略 null 字段。
        // 实测证明 kotlinx.serialization 对"可空但无默认值"的字段在缺失时按 null 解码、
        // 不抛异常（与本 prompt 最初的纸面推导相反，以运行时地面真相为准）。
        // 因此全 null 的 MonitorState 可以完整往返。
        val state = MonitorState(
            current = null,
            next = null,
            remainingMs = null,
            rehearsal = false,
            serverTimeMs = 1234L
        )
        val json = WsJson.json.encodeToString(MonitorState.serializer(), state)
        val decoded = WsJson.json.decodeFromString(MonitorState.serializer(), json)
        assertEquals(state, decoded)
        assertNull(decoded.current)
        assertNull(decoded.next)
        assertNull(decoded.remainingMs)
    }

    @Test
    fun monitorStateFullRoundTrip() {
        val current = Cue("c1", "当前", CueType.AUDIO, order = 1)
        val next = Cue("c2", "下一个", CueType.PROMPT, order = 2)
        val state = MonitorState(
            current = current,
            next = next,
            remainingMs = 1500L,
            rehearsal = true,
            serverTimeMs = 9999L
        )
        val json = WsJson.json.encodeToString(MonitorState.serializer(), state)
        val decoded = WsJson.json.decodeFromString(MonitorState.serializer(), json)
        assertEquals(state, decoded)
        assertNotNull(decoded.current)
        assertNotNull(decoded.next)
        assertEquals("c1", decoded.current?.id)
        assertEquals("c2", decoded.next?.id)
        assertEquals(1500L, decoded.remainingMs)
    }

    @Test
    fun cueCopyPreservesType() {
        val cue = Cue("c1", "开场", CueType.LIGHT, order = 1)
        val c2 = cue.copy(order = 9)
        assertEquals(9, c2.order)
        assertEquals(cue.type, c2.type)
        assertEquals(CueType.LIGHT, c2.type)
    }
}
