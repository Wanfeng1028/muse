package dev.stagecue.server

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import dev.stagecue.shared.oplog.InMemoryOpLogStore

class SyncHubMissedOpsTest {

    @Test
    fun `missedOps returns empty list when opLog is not configured`() {
        val hub = SyncHub()

        val result = hub.missedOps(0)

        assertTrue(result.isEmpty())
        assertEquals(0, result.size)
    }

    @Test
    fun `missedOps returns empty list for null lastSeenSeq even with three entries`() {
        val opLog = InMemoryOpLogStore()
        opLog.append("TriggerCue", "cue-a", "first")
        opLog.append("ArmCue", "cue-b", "second")
        opLog.append("SetRehearsal", null, "third")
        val hub = SyncHub(opLog = opLog)

        val result = hub.missedOps(null)

        assertTrue(result.isEmpty())
        assertEquals(0, result.size)
    }

    @Test
    fun `missedOps with lastSeenSeq zero returns all three entries in ascending seq order`() {
        val opLog = InMemoryOpLogStore()
        opLog.append("TriggerCue", "cue-a", "first")
        opLog.append("ArmCue", "cue-b", "second")
        opLog.append("SetRehearsal", null, "third")
        val hub = SyncHub(opLog = opLog)

        val result = hub.missedOps(0)

        assertEquals(3, result.size)
        assertEquals(listOf(1L, 2L, 3L), result.map { it.seq })
    }

    @Test
    fun `missedOps with lastSeenSeq two returns only the third entry`() {
        val opLog = InMemoryOpLogStore()
        opLog.append("TriggerCue", "cue-a", "first")
        opLog.append("ArmCue", "cue-b", "second")
        opLog.append("SetRehearsal", null, "third")
        val hub = SyncHub(opLog = opLog)

        val result = hub.missedOps(2)

        assertEquals(1, result.size)
        assertEquals(3L, result.single().seq)
    }

    @Test
    fun `missedOps with lastSeenSeq equal to max seq returns empty list`() {
        val opLog = InMemoryOpLogStore()
        opLog.append("TriggerCue", "cue-a", "first")
        opLog.append("ArmCue", "cue-b", "second")
        opLog.append("SetRehearsal", null, "third")
        val hub = SyncHub(opLog = opLog)

        val result = hub.missedOps(3)

        assertTrue(result.isEmpty())
        assertEquals(0, result.size)
    }

    @Test
    fun `missedOps preserves type and cueId from append`() {
        val opLog = InMemoryOpLogStore()
        opLog.append("TriggerCue", "cue-a", "first")
        opLog.append("ArmCue", "cue-b", "second")
        opLog.append("SetRehearsal", null, "third")
        val hub = SyncHub(opLog = opLog)

        val result = hub.missedOps(0)

        assertEquals(3, result.size)
        assertEquals("TriggerCue", result.first().type)
        assertEquals("cue-a", result.first().cueId)
    }

    @Test
    fun `missedOps returns empty list when opLog is configured but has no entries`() {
        val hub = SyncHub(opLog = InMemoryOpLogStore())

        val result = hub.missedOps(0)

        assertTrue(result.isEmpty())
        assertEquals(0, result.size)
    }
}
