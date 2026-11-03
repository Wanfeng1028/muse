package dev.stagecue.server

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import dev.stagecue.shared.model.*
import dev.stagecue.shared.protocol.TriggerCue

class MonitorSnapshotBoundaryTest {

    private fun show(cues: List<Cue>) = Show(
        id = "s1",
        name = "t",
        cues = cues,
        createdAtMs = 0,
        updatedAtMs = 0,
    )

    private fun cue(id: String, order: Int, durationMs: Long = 0) = Cue(
        id = id,
        name = id,
        type = CueType.AUDIO,
        durationMs = durationMs,
        order = order,
    )

    @Test
    fun neverFired_currentNull_nextLowestOrder_remainingNull_serverTimeEchoed() {
        val hub = SyncHub(clock = { 1_000_000L })
        val s = show(listOf(cue("c1", 1), cue("c2", 2)))

        val snap = hub.monitorSnapshot(s, nowMs = 5_000_000L)

        assertNull(snap.current)
        assertNotNull(snap.next)
        assertEquals("c1", snap.next!!.id)
        assertEquals(1, snap.next!!.order)
        assertNull(snap.remainingMs)
        assertEquals(5_000_000L, snap.serverTimeMs)
    }

    @Test
    fun firedC1_remainingMidway_andNextIsOrder2() {
        val hub = SyncHub(clock = { 1_000_000L })
        val s = show(listOf(cue("c1", 1, 60_000), cue("c2", 2)))

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 1_000_000L, cueId = "c1"))
        val snap = hub.monitorSnapshot(s, nowMs = 1_030_000L)

        assertNotNull(snap.current)
        assertEquals("c1", snap.current!!.id)
        assertEquals(30_000L, snap.remainingMs)
        assertNotNull(snap.next)
        assertEquals("c2", snap.next!!.id)
        assertEquals(2, snap.next!!.order)
        assertEquals(1_030_000L, snap.serverTimeMs)
    }

    @Test
    fun remainingClampedToZero_whenElapsedExceedsDuration() {
        val hub = SyncHub(clock = { 1_000_000L })
        val s = show(listOf(cue("c1", 1, 60_000), cue("c2", 2)))

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 1_000_000L, cueId = "c1"))
        val snap = hub.monitorSnapshot(s, nowMs = 1_070_000L)

        assertEquals(0L, snap.remainingMs)
        assertNotNull(snap.current)
        assertEquals("c1", snap.current!!.id)
    }

    @Test
    fun remainingExactlyZero_atExactDurationBoundary() {
        val hub = SyncHub(clock = { 1_000_000L })
        val s = show(listOf(cue("c1", 1, 60_000)))

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 1_000_000L, cueId = "c1"))
        val snap = hub.monitorSnapshot(s, nowMs = 1_060_000L)

        assertEquals(0L, snap.remainingMs)
    }

    @Test
    fun zeroDurationCue_remainingNull() {
        val hub = SyncHub(clock = { 1_000_000L })
        val s = show(listOf(cue("c1", 1, 0), cue("c2", 2)))

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 1_000_000L, cueId = "c1"))
        val snap = hub.monitorSnapshot(s, nowMs = 1_005_000L)

        assertNotNull(snap.current)
        assertEquals("c1", snap.current!!.id)
        assertNull(snap.remainingMs)
        assertEquals("c2", snap.next!!.id)
    }

    @Test
    fun firedLastOrderedCue_nextNull() {
        val hub = SyncHub(clock = { 1_000_000L })
        val s = show(listOf(cue("c1", 1, 60_000), cue("c2", 2, 60_000), cue("c3", 3, 60_000)))

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 1_000_000L, cueId = "c3"))
        val snap = hub.monitorSnapshot(s, nowMs = 1_010_000L)

        assertNotNull(snap.current)
        assertEquals("c3", snap.current!!.id)
        assertNull(snap.next)
    }

    @Test
    fun firedCueMissingFromShow_currentNull_nextFallsBackToLowestOrder() {
        val hub = SyncHub(clock = { 1_000_000L })
        val sWithC1 = show(listOf(cue("c1", 1, 60_000), cue("c2", 2)))
        val sWithoutC1 = show(listOf(cue("c2", 2, 60_000), cue("c3", 3)))

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 1_000_000L, cueId = "c1"))
        val snap = hub.monitorSnapshot(sWithoutC1, nowMs = 1_030_000L)

        assertNull(snap.current)
        assertNotNull(snap.next)
        assertEquals("c2", snap.next!!.id)
        assertEquals(2, snap.next!!.order)
        assertNull(snap.remainingMs)
    }

    @Test
    fun noSettings_setRehearsal_doesNotAffectSnapshotRehearsal() {
        val hub = SyncHub(clock = { 1_000_000L })
        val s = show(listOf(cue("c1", 1, 60_000)))

        hub.setRehearsal(true)
        val snap = hub.monitorSnapshot(s, nowMs = 1_000_000L)

        assertFalse(snap.rehearsal)
    }

    @Test
    fun unsortedCues_nextSelectedByOrderAscending() {
        val hub = SyncHub(clock = { 1_000_000L })
        val s = show(listOf(cue("c3", 3), cue("c1", 1), cue("c2", 2)))

        val neverFired = hub.monitorSnapshot(s, nowMs = 1_000_000L)
        assertNull(neverFired.current)
        assertEquals("c1", neverFired.next!!.id)
        assertEquals(1, neverFired.next!!.order)

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 1_000_000L, cueId = "c1"))
        val afterC1 = hub.monitorSnapshot(s, nowMs = 1_000_000L)
        assertEquals("c1", afterC1.current!!.id)
        assertEquals("c2", afterC1.next!!.id)
        assertEquals(2, afterC1.next!!.order)

        hub.handleTriggerCue(TriggerCue(msgId = "m2", sentAtMs = 1_000_000L, cueId = "c2"))
        val afterC2 = hub.monitorSnapshot(s, nowMs = 1_000_000L)
        assertEquals("c3", afterC2.next!!.id)
        assertEquals(3, afterC2.next!!.order)
    }

    @Test
    fun mutableClock_remainingTracksLastFiredAtMsOfMostRecentTrigger() {
        var now = 1_000_000L
        val hub = SyncHub(clock = { now })
        val s = show(listOf(cue("c1", 1, 60_000), cue("c2", 2, 30_000), cue("c3", 3)))

        hub.handleTriggerCue(TriggerCue(msgId = "m1", sentAtMs = 1_000_000L, cueId = "c1"))
        now = 1_010_000L
        hub.handleTriggerCue(TriggerCue(msgId = "m2", sentAtMs = 1_010_000L, cueId = "c2"))

        now = 1_020_000L
        val snap = hub.monitorSnapshot(s, nowMs = 1_020_000L)

        assertEquals("c2", snap.current!!.id)
        assertEquals(20_000L, snap.remainingMs)
        assertEquals("c3", snap.next!!.id)
    }
}