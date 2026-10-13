package dev.stagecue.server

import dev.stagecue.shared.protocol.*
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class SyncHubTest {

    @Test
    fun `hello returns welcome with clientId and serverTimeMs`() {
        var now = 1000L
        val hub = SyncHub(clock = { now })
        val hello = Hello(
            msgId = "m1",
            sentAtMs = 900,
            clientId = "client-A",
            role = ClientRole.DIRECTOR,
            clientTimeMs = 950,
        )
        val welcome = hub.handleConnect(hello.clientId, hello.role)
        assertEquals("client-A", welcome.clientId)
        assertEquals(1000L, welcome.serverTimeMs)
    }

    @Test
    fun `clock ping returns pong echoing seq and clientTimeMs`() {
        var now = 2000L
        val hub = SyncHub(clock = { now })
        val ping = ClockPing(
            msgId = "m2",
            sentAtMs = 900,
            seq = 7,
            clientTimeMs = 4500,
        )
        val pong = hub.handleClockPing(ping)
        assertEquals(7L, pong.seq)
        assertEquals(4500L, pong.clientTimeMs)
        assertEquals(2000L, pong.serverTimeMs)
    }

    @Test
    fun `trigger cue is idempotent by msgId`() {
        var now = 3000L
        val hub = SyncHub(clock = { now })
        val cue = TriggerCue(
            msgId = "evt-1",
            sentAtMs = 1000,
            cueId = "cue-001",
        )
        val first = hub.handleTriggerCue(cue)
        assertInstanceOf(CueFired::class.java, first)
        val second = hub.handleTriggerCue(cue)
        assertInstanceOf(Error::class.java, second)
    }

    @Test
    fun `different msgId triggers a new cue fired with matching eventId`() {
        var now = 4000L
        val hub = SyncHub(clock = { now })
        hub.handleTriggerCue(
            TriggerCue(msgId = "evt-1", sentAtMs = 1000, cueId = "cue-001"),
        )
        val out = hub.handleTriggerCue(
            TriggerCue(msgId = "e2", sentAtMs = 1100, cueId = "cue-001"),
        )
        assertInstanceOf(CueFired::class.java, out)
        assertEquals("e2", (out as CueFired).eventId)
    }

    @Test
    fun `arm cue returns cue armed with cueId`() {
        var now = 5000L
        val hub = SyncHub(clock = { now })
        val arm = ArmCue(
            msgId = "m5",
            sentAtMs = 1200,
            cueId = "cue-002",
        )
        val armed = hub.handleArmCue(arm)
        assertEquals("cue-002", armed.cueId)
    }
}
