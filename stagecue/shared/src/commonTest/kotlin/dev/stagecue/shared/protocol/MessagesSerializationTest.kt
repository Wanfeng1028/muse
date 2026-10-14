package dev.stagecue.shared.protocol

import dev.stagecue.shared.model.CueState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class MessagesSerializationTest {

    private val json = WsJson.json

    @Test
    fun roundTripHello() {
        val msg: WsMessage = Hello(
            msgId = "m1",
            sentAtMs = 1000L,
            clientId = "c1",
            role = ClientRole.DIRECTOR,
            clientTimeMs = 999L
        )
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripClockPing() {
        val msg: WsMessage = ClockPing(msgId = "m2", sentAtMs = 2000L, seq = 7L, clientTimeMs = 1999L)
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripClockPong() {
        val msg: WsMessage = ClockPong(
            msgId = "m3",
            sentAtMs = 3000L,
            seq = 7L,
            clientTimeMs = 1999L,
            serverTimeMs = 2100L
        )
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripTriggerCueWithNullFireAt() {
        val msg: WsMessage = TriggerCue(
            msgId = "m4",
            sentAtMs = 4000L,
            cueId = "cue-1",
            fireAtServerMs = null
        )
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripTriggerCueWithFireAt() {
        val msg: WsMessage = TriggerCue(
            msgId = "m5",
            sentAtMs = 4000L,
            cueId = "cue-1",
            fireAtServerMs = 4500L
        )
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripArmCue() {
        val msg: WsMessage = ArmCue(msgId = "m6", sentAtMs = 5000L, cueId = "cue-2")
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripWelcome() {
        val msg: WsMessage = Welcome(msgId = "m7", sentAtMs = 6000L, clientId = "c1", serverTimeMs = 6100L)
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripCueFired() {
        val msg: WsMessage = CueFired(
            msgId = "m8",
            sentAtMs = 7000L,
            cueId = "cue-1",
            firedAtServerMs = 7100L,
            eventId = "evt-1"
        )
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripSetRehearsal() {
        val msg: WsMessage = SetRehearsal(msgId = "m14", sentAtMs = 14000L, enabled = true)
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripRehearsalChanged() {
        val msg: WsMessage = RehearsalChanged(msgId = "m15", sentAtMs = 15000L, enabled = false)
        val text = json.encodeToString(WsMessage.serializer(), msg)
        assertTrue(text.contains("\"kind\":\"rehearsal_changed\""), "expected kind in $text")
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripCueFiredRehearsal() {
        val msg: WsMessage = CueFired(
            msgId = "m16", sentAtMs = 16000L, cueId = "cue-1",
            firedAtServerMs = 16100L, eventId = "evt-2", rehearsal = true
        )
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun cueFiredWithoutRehearsalFieldDefaultsFalse() {
        // 老版本消息没有 rehearsal 字段，反序列化必须兼容
        val raw = """{"kind":"cue_fired","msgId":"m17","sentAtMs":17000,"cueId":"c","firedAtServerMs":17100,"eventId":"e"}"""
        val msg = json.decodeFromString(WsMessage.serializer(), raw) as CueFired
        assertEquals(false, msg.rehearsal)
    }

    @Test
    fun roundTripCueArmed() {
        val msg: WsMessage = CueArmed(msgId = "m9", sentAtMs = 8000L, cueId = "cue-3")
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripStateSnapshot() {
        val msg: WsMessage = StateSnapshot(
            msgId = "m10",
            sentAtMs = 9000L,
            showId = "show-1",
            states = mapOf(
                "cue-1" to CueState.DONE,
                "cue-2" to CueState.ARMED,
                "cue-3" to CueState.IDLE
            ),
            serverTimeMs = 9100L
        )
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun roundTripError() {
        val msg: WsMessage = Error(msgId = "m11", sentAtMs = 10000L, code = "E_AUTH", message = "denied")
        val text = json.encodeToString(WsMessage.serializer(), msg)
        val back = json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, back)
    }

    @Test
    fun unknownKeysAreIgnored() {
        val raw = """
            {"kind":"clock_ping","msgId":"m12","sentAtMs":12000,"seq":1,"clientTimeMs":12000,"extra":"ignored"}
        """.trimIndent()
        val msg = json.decodeFromString(WsMessage.serializer(), raw)
        assertEquals(
            ClockPing(msgId = "m12", sentAtMs = 12000L, seq = 1L, clientTimeMs = 12000L),
            msg
        )
    }

    @Test
    fun discriminatorIsKind() {
        val msg: WsMessage = ClockPing(msgId = "m13", sentAtMs = 13000L, seq = 2L, clientTimeMs = 13000L)
        val text = json.encodeToString(WsMessage.serializer(), msg)
        kotlin.test.assertTrue(text.contains("\"kind\":\"clock_ping\""), "expected kind discriminator in $text")
    }
}
