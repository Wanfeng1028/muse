package dev.stagecue.server

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import dev.stagecue.shared.protocol.*

class AuthorizeWriteMatrixTest {

    private val hub = SyncHub()

    private fun triggerCue() = TriggerCue(
        msgId = "m-trigger",
        sentAtMs = 1_000L,
        cueId = "cue-1"
    )

    private fun armCue() = ArmCue(
        msgId = "m-arm",
        sentAtMs = 1_000L,
        cueId = "cue-1"
    )

    private fun setRehearsal() = SetRehearsal(
        msgId = "m-reh",
        sentAtMs = 1_000L,
        enabled = true
    )

    private fun hello() = Hello(
        msgId = "m-hello",
        sentAtMs = 1_000L,
        clientId = "client-1",
        role = ClientRole.MONITOR,
        clientTimeMs = 1_000L
    )

    private fun clockPing() = ClockPing(
        msgId = "m-ping",
        sentAtMs = 1_000L,
        seq = 1L,
        clientTimeMs = 1_000L
    )

    @Test
    fun `MONITOR trigger_cue is forbidden with trigger_cue action in message`() {
        val err = hub.authorizeWrite(ClientRole.MONITOR, triggerCue())
        assertNotNull(err)
        assertEquals("FORBIDDEN", err!!.code)
        assertTrue(err.message.contains("trigger_cue"))
        assertEquals("role MONITOR is read-only; trigger_cue requires DIRECTOR", err.message)
    }

    @Test
    fun `MONITOR arm_cue is forbidden with arm_cue action in message`() {
        val err = hub.authorizeWrite(ClientRole.MONITOR, armCue())
        assertNotNull(err)
        assertEquals("FORBIDDEN", err!!.code)
        assertTrue(err.message.contains("arm_cue"))
        assertEquals("role MONITOR is read-only; arm_cue requires DIRECTOR", err.message)
    }

    @Test
    fun `MONITOR set_rehearsal is forbidden with set_rehearsal action in message`() {
        val err = hub.authorizeWrite(ClientRole.MONITOR, setRehearsal())
        assertNotNull(err)
        assertEquals("FORBIDDEN", err!!.code)
        assertTrue(err.message.contains("set_rehearsal"))
        assertEquals("role MONITOR is read-only; set_rehearsal requires DIRECTOR", err.message)
    }

    @Test
    fun `MONITOR hello and clock_ping are allowed for handshake and sync`() {
        assertNull(hub.authorizeWrite(ClientRole.MONITOR, hello()))
        assertNull(hub.authorizeWrite(ClientRole.MONITOR, clockPing()))
    }

    @Test
    fun `DIRECTOR all three write actions are allowed`() {
        assertNull(hub.authorizeWrite(ClientRole.DIRECTOR, triggerCue()))
        assertNull(hub.authorizeWrite(ClientRole.DIRECTOR, armCue()))
        assertNull(hub.authorizeWrite(ClientRole.DIRECTOR, setRehearsal()))
    }

    @Test
    fun `LIGHTING trigger_cue and set_rehearsal are allowed`() {
        assertNull(hub.authorizeWrite(ClientRole.LIGHTING, triggerCue()))
        assertNull(hub.authorizeWrite(ClientRole.LIGHTING, setRehearsal()))
    }

    @Test
    fun `null role legacy behavior allows trigger_cue`() {
        assertNull(hub.authorizeWrite(null, triggerCue()))
    }

    @Test
    fun `FORBIDDEN error carries non-empty msgId and positive sentAtMs`() {
        val err = hub.authorizeWrite(ClientRole.MONITOR, triggerCue())
        assertNotNull(err)
        assertTrue(err!!.msgId.isNotEmpty())
        assertTrue(err.sentAtMs > 0L)
    }
}