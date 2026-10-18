package dev.stagecue.shared.protocol

import kotlinx.serialization.SerializationException
import dev.stagecue.shared.oplog.OpLogEntry
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class WsMessageOpLogReplayDeepTest {

    @Test
    fun roundTripOpLogReplay() {
        val msg = OpLogReplay(
            msgId = "m1",
            sentAtMs = 1000L,
            entries = listOf(
                OpLogEntry(
                    seq = 1L,
                    eventId = "e1",
                    type = "CUE_FIRED",
                    cueId = "c1",
                    atMs = 900L,
                    detail = "d1"
                ),
                OpLogEntry(
                    seq = 2L,
                    eventId = "e2",
                    type = "REHEARSAL_MODE",
                    cueId = null,
                    atMs = 950L
                )
            )
        )
        val text = WsJson.json.encodeToString(WsMessage.serializer(), msg)
        val decoded = WsJson.json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, decoded)
    }

    @Test
    fun opLogReplayDiscriminatorIsKind() {
        val msg = OpLogReplay(
            msgId = "m1",
            sentAtMs = 1000L,
            entries = listOf(
                OpLogEntry(
                    seq = 1L,
                    eventId = "e1",
                    type = "CUE_FIRED",
                    cueId = "c1",
                    atMs = 900L,
                    detail = "d1"
                )
            )
        )
        val text = WsJson.json.encodeToString(WsMessage.serializer(), msg)
        assertTrue(text.contains("\"kind\":\"oplog_replay\""))
    }

    @Test
    fun helloLastSeenSeqRoundTrip() {
        val msg = Hello(
            msgId = "h1",
            sentAtMs = 2000L,
            clientId = "client-1",
            role = ClientRole.DIRECTOR,
            clientTimeMs = 1900L,
            lastSeenSeq = 42L
        )
        val text = WsJson.json.encodeToString(WsMessage.serializer(), msg)
        val decoded = WsJson.json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, decoded)
        assertEquals(42L, (decoded as Hello).lastSeenSeq)
    }

    @Test
    fun helloWithoutLastSeenSeqDecodesToNull() {
        val text = "{\"kind\":\"hello\",\"msgId\":\"m\",\"sentAtMs\":1,\"clientId\":\"c\",\"role\":\"DIRECTOR\",\"clientTimeMs\":2}"
        val decoded = WsJson.json.decodeFromString(WsMessage.serializer(), text)
        assertTrue(decoded is Hello)
        assertNull((decoded as Hello).lastSeenSeq)
    }

    @Test
    fun unknownKindThrows() {
        val text = "{\"kind\":\"nope\",\"msgId\":\"m\",\"sentAtMs\":1}"
        assertFailsWith<SerializationException> {
            WsJson.json.decodeFromString(WsMessage.serializer(), text)
        }
    }

    @Test
    fun opLogReplayEmptyEntries() {
        val msg = OpLogReplay(
            msgId = "m-empty",
            sentAtMs = 500L,
            entries = emptyList()
        )
        val text = WsJson.json.encodeToString(WsMessage.serializer(), msg)
        assertTrue(text.contains("\"entries\":[]"))
        val decoded = WsJson.json.decodeFromString(WsMessage.serializer(), text)
        assertEquals(msg, decoded)
    }

    @Test
    fun unknownKeysIgnoredInOpLogReplay() {
        val text = "{\"kind\":\"oplog_replay\",\"msgId\":\"m1\",\"sentAtMs\":1000,\"entries\":[{\"seq\":1,\"eventId\":\"e1\",\"type\":\"CUE_FIRED\",\"cueId\":\"c1\",\"atMs\":900,\"detail\":\"d1\"}],\"zzz\":123}"
        val decoded = WsJson.json.decodeFromString(WsMessage.serializer(), text)
        assertTrue(decoded is OpLogReplay)
        assertEquals(
            OpLogReplay(
                msgId = "m1",
                sentAtMs = 1000L,
                entries = listOf(
                    OpLogEntry(
                        seq = 1L,
                        eventId = "e1",
                        type = "CUE_FIRED",
                        cueId = "c1",
                        atMs = 900L,
                        detail = "d1"
                    )
                )
            ),
            decoded
        )
    }
}
