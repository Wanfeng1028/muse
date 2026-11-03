package dev.stagecue.server

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import dev.stagecue.shared.oplog.InMemoryOpLogStore
import dev.stagecue.shared.oplog.FileOpLogStore
import dev.stagecue.shared.protocol.*
import java.io.File

class SyncHubReplayBoundaryTest {

    @Test
    fun `replay after reconnect delivers each missed op exactly once and repeated query is stable`() {
        val opLog = InMemoryOpLogStore()
        val hub = SyncHub(opLog = opLog)

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 0L, cueId = "cue-1"))
        hub.handleTriggerCue(TriggerCue(msgId = "m2", sentAtMs = 0L, cueId = "cue-2"))
        hub.handleTriggerCue(TriggerCue(msgId = "m3", sentAtMs = 0L, cueId = "cue-3"))
        hub.handleTriggerCue(TriggerCue(msgId = "m4", sentAtMs = 0L, cueId = "cue-4"))
        hub.handleTriggerCue(TriggerCue(msgId = "m5", sentAtMs = 0L, cueId = "cue-5"))

        val first = hub.missedOps(2L)
        assertEquals(3, first.size)
        assertEquals(listOf(3L, 4L, 5L), first.map { it.seq })
        assertEquals(3, first.map { it.seq }.distinct().size)

        val second = hub.missedOps(2L)
        assertEquals(first.map { it.seq }, second.map { it.seq })
        assertEquals(first.map { it.eventId }, second.map { it.eventId })
    }

    @Test
    fun `mid session disconnect replays only the ops appended after last seen seq`() {
        val opLog = InMemoryOpLogStore()
        val hub = SyncHub(opLog = opLog)

        hub.handleTriggerCue(TriggerCue(msgId = "a1", sentAtMs = 0L, cueId = "cue-a"))
        hub.handleTriggerCue(TriggerCue(msgId = "a2", sentAtMs = 0L, cueId = "cue-b"))
        hub.handleTriggerCue(TriggerCue(msgId = "a3", sentAtMs = 0L, cueId = "cue-c"))

        hub.handleTriggerCue(TriggerCue(msgId = "b1", sentAtMs = 0L, cueId = "cue-d"))
        hub.handleTriggerCue(TriggerCue(msgId = "b2", sentAtMs = 0L, cueId = "cue-e"))
        hub.handleTriggerCue(TriggerCue(msgId = "b3", sentAtMs = 0L, cueId = "cue-f"))

        val result = hub.missedOps(3L)

        assertEquals(3, result.size)
        assertEquals(listOf(4L, 5L, 6L), result.map { it.seq })
        assertEquals(result.map { it.seq }.sorted(), result.map { it.seq })
    }

    @Test
    fun `replay is empty for fresh file store and for hub without opLog`(@TempDir dir: File) {
        val fileHub = SyncHub(opLog = FileOpLogStore(dir))

        val fileResult = fileHub.missedOps(0L)
        assertTrue(fileResult.isEmpty())
        assertEquals(0, fileResult.size)

        val hubWithoutLog = SyncHub()

        val noLogResult = hubWithoutLog.missedOps(5L)
        assertTrue(noLogResult.isEmpty())
        assertEquals(0, noLogResult.size)
    }

    @Test
    fun `replay is empty when last seen seq equals max seq and when it is far beyond max`() {
        val opLog = InMemoryOpLogStore()
        opLog.append("CUE_FIRED", "cue-1", "d1")
        opLog.append("CUE_FIRED", "cue-2", "d2")
        opLog.append("CUE_FIRED", "cue-3", "d3")
        val hub = SyncHub(opLog = opLog)

        val atMax = hub.missedOps(3L)
        assertTrue(atMax.isEmpty())
        assertEquals(0, atMax.size)

        val beyondMax = hub.missedOps(999L)
        assertTrue(beyondMax.isEmpty())
        assertEquals(0, beyondMax.size)
    }

    @Test
    fun `negative last seen seq replays every entry because all seqs are greater`() {
        val opLog = InMemoryOpLogStore()
        opLog.append("CUE_FIRED", "cue-1", "d1")
        opLog.append("CUE_FIRED", "cue-2", "d2")
        opLog.append("CUE_FIRED", "cue-3", "d3")
        val hub = SyncHub(opLog = opLog)

        val result = hub.missedOps(-1L)

        assertEquals(3, result.size)
        assertEquals(listOf(1L, 2L, 3L), result.map { it.seq })
    }

    @Test
    fun `file store continues seq across restart and replays the tail`(@TempDir dir: File) {
        val first = FileOpLogStore(dir)
        val e1 = first.append("CUE_FIRED", "cue-1", "d1")
        val e2 = first.append("CUE_FIRED", "cue-2", "d2")
        val e3 = first.append("CUE_FIRED", "cue-3", "d3")
        assertEquals(1L, e1.seq)
        assertEquals(2L, e2.seq)
        assertEquals(3L, e3.seq)

        val second = FileOpLogStore(dir)
        val e4 = second.append("CUE_FIRED", "cue-4", "d4")
        assertEquals(4L, e4.seq)

        val hub = SyncHub(opLog = second)
        val result = hub.missedOps(1L)

        assertEquals(3, result.size)
        assertEquals(listOf(2L, 3L, 4L), result.map { it.seq })
    }

    @Test
    fun `duplicate trigger cue returns duplicate error and does not append a second op`() {
        val opLog = InMemoryOpLogStore()
        val hub = SyncHub(opLog = opLog)

        val first = hub.handleTriggerCue(TriggerCue(msgId = "dup-1", sentAtMs = 0L, cueId = "cue-x"))
        assertTrue(first is CueFired)

        val second = hub.handleTriggerCue(TriggerCue(msgId = "dup-1", sentAtMs = 0L, cueId = "cue-x"))
        assertTrue(second is Error)
        assertEquals("DUPLICATE_EVENT", (second as Error).code)

        assertEquals(1, opLog.readAll().size)
        assertEquals(1, hub.missedOps(0L).size)
    }
}
