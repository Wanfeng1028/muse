package dev.stagecue.server

import dev.stagecue.shared.protocol.CueFired
import dev.stagecue.shared.protocol.Error
import dev.stagecue.shared.protocol.TriggerCue
import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.model.Show
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class SyncHubTriggerSnapshotDeepTest {

    private fun cue(
        id: String,
        order: Int,
        durationMs: Long = 0L,
    ): Cue = Cue(
        id = id,
        name = id,
        type = CueType.AUDIO,
        durationMs = durationMs,
        order = order,
    )

    private fun show(vararg cues: Cue): Show = Show(
        id = "show-1",
        name = "Show",
        cues = cues.toList(),
        createdAtMs = 0L,
        updatedAtMs = 0L,
    )

    private fun TriggerCue.toTriggerCue() = TriggerCue(msgId, cueId)

    private fun TriggerCue(msgId: String, cueId: String) = dev.stagecue.shared.protocol.TriggerCue(
        msgId = msgId,
        sentAtMs = 0L,
        cueId = cueId,
    )

    @Test
    fun `duplicate trigger does not move lastFiredAtMs`() {
        // now=1000: first trigger accepted, lastFiredAtMs := 1000
        var now = 1000L
        val hub = SyncHub(clock = { now })
        val first = hub.handleTriggerCue(TriggerCue("e1", "c1"))
        assertTrue(first is CueFired)

        // now=2000: duplicate msgId, must be rejected and must NOT touch lastFiredAtMs
        now = 2000L
        val second = hub.handleTriggerCue(TriggerCue("e1", "c1"))
        assertTrue(second is Error)
        assertEquals("DUPLICATE_EVENT", (second as Error).code)

        // remaining = duration - (nowMs - lastFiredAtMs) = 10000 - (2500 - 1000) = 8500
        // If dedup had moved lastFiredAtMs to 2000 it would be 10000 - (2500 - 2000) = 9500.
        val state = hub.monitorSnapshot(show(cue("c1", order = 1, durationMs = 10_000L)), nowMs = 2500L)
        assertEquals(8500L, state.remainingMs)
    }

    @Test
    fun `snapshot sorts cues by order`() {
        var now = 0L
        val hub = SyncHub(clock = { now })
        now = 1000L
        hub.handleTriggerCue(TriggerCue("e1", "c1"))

        // cues intentionally out of order: order=5 (c3), order=1 (c1), order=3 (c2)
        val s = show(
            cue("c3", order = 5),
            cue("c1", order = 1),
            cue("c2", order = 3),
        )
        val state = hub.monitorSnapshot(s, nowMs = 1000L)
        assertEquals("c1", state.current?.id)
        // next = smallest order strictly greater than current.order (1) => order=3 => c2
        assertEquals("c2", state.next?.id)
    }

    @Test
    fun `remainingMs clamps at zero when elapsed exceeds duration`() {
        var now = 0L
        val hub = SyncHub(clock = { now })
        // trigger at now=0
        hub.handleTriggerCue(TriggerCue("e1", "c1"))

        // nowMs=5000, duration=1000 => 1000 - 5000 = -4000 => clamped to 0
        val state = hub.monitorSnapshot(show(cue("c1", order = 1, durationMs = 1_000L)), nowMs = 5000L)
        assertEquals(0L, state.remainingMs)
    }

    @Test
    fun `remainingMs counts down exactly`() {
        var now = 0L
        val hub = SyncHub(clock = { now })
        now = 1000L
        hub.handleTriggerCue(TriggerCue("e1", "c1"))

        // 10000 - (2500 - 1000) = 8500
        val state = hub.monitorSnapshot(show(cue("c1", order = 1, durationMs = 10_000L)), nowMs = 2500L)
        assertEquals(8500L, state.remainingMs)
    }

    @Test
    fun `fired unknown cue id yields null current and first next`() {
        var now = 0L
        val hub = SyncHub(clock = { now })
        now = 1000L
        hub.handleTriggerCue(TriggerCue("e1", "ghost"))

        val s = show(
            cue("c2", order = 3),
            cue("c1", order = 1),
            cue("c3", order = 5),
        )
        val state = hub.monitorSnapshot(s, nowMs = 1000L)
        assertNull(state.current)
        // current==null => next = smallest order overall => c1 (order=1)
        assertEquals("c1", state.next?.id)
    }

    @Test
    fun `firing last cue yields null next`() {
        var now = 0L
        val hub = SyncHub(clock = { now })
        now = 1000L
        hub.handleTriggerCue(TriggerCue("e1", "c3"))

        val s = show(
            cue("c1", order = 1),
            cue("c2", order = 3),
            cue("c3", order = 5),
        )
        val state = hub.monitorSnapshot(s, nowMs = 1000L)
        assertEquals("c3", state.current?.id)
        assertNull(state.next)
    }

    @Test
    fun `empty show snapshot`() {
        var now = 0L
        val hub = SyncHub(clock = { now })
        now = 1000L
        hub.handleTriggerCue(TriggerCue("e1", "c1"))

        val state = hub.monitorSnapshot(show(), nowMs = 1000L)
        assertNull(state.current)
        assertNull(state.next)
        assertNull(state.remainingMs)
    }

    @Test
    fun `snapshot serverTimeMs equals nowMs param`() {
        var now = 0L
        val hub = SyncHub(clock = { now })

        val state = hub.monitorSnapshot(show(cue("c1", order = 1, durationMs = 10_000L)), nowMs = 4242L)
        assertEquals(4242L, state.serverTimeMs)
    }

    @Test
    fun `second trigger moves current`() {
        var now = 0L
        val hub = SyncHub(clock = { now })

        // trigger c1 at now=1000
        now = 1000L
        hub.handleTriggerCue(TriggerCue("e1", "c1"))

        // trigger c2 at now=2000 (different msgId) => lastFiredCueId=c2, lastFiredAtMs=2000
        now = 2000L
        hub.handleTriggerCue(TriggerCue("e2", "c2"))

        // duration=10000 => 10000 - (2000 - 2000) = 10000
        val s = show(
            cue("c1", order = 1, durationMs = 10_000L),
            cue("c2", order = 3, durationMs = 10_000L),
        )
        val state = hub.monitorSnapshot(s, nowMs = 2000L)
        assertEquals("c2", state.current?.id)
        assertEquals(10_000L, state.remainingMs)
    }
}
