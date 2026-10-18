package dev.stagecue.desktop.sync

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

class DirectorClientDeepTest {

    @Test
    fun `initial state is disconnected`() {
        val client = DirectorClient()
        assertEquals(ConnState.DISCONNECTED, client.connState.value)
    }

    @Test
    fun `initial rehearsal mode is false`() {
        val client = DirectorClient()
        assertFalse(client.rehearsalMode.value)
    }

    @Test
    fun `initial cues and states are empty`() {
        val client = DirectorClient()
        assertTrue(client.cues.value.isEmpty())
        assertTrue(client.states.value.isEmpty())
        assertNull(client.serverTimeMs.value)
    }

    @Test
    fun `log keeps last 200 entries`() {
        val client = DirectorClient()
        for (i in 0 until 250) {
            client.log("m$i")
        }
        assertEquals(200, client.log.value.size)
        assertEquals("m50", client.log.value.first())
        assertEquals("m249", client.log.value.last())
    }

    @Test
    fun `triggerCue when disconnected logs warning`() {
        val client = DirectorClient()
        client.triggerCue("c1")
        assertEquals("未连接，无法触发 cue", client.log.value.last())
    }

    @Test
    fun `armCue when disconnected logs warning`() {
        val client = DirectorClient()
        client.armCue("c1")
        assertEquals("未连接，无法预备 cue", client.log.value.last())
    }

    @Test
    fun `setRehearsal when disconnected logs warning`() {
        val client = DirectorClient()
        client.setRehearsal(true)
        assertEquals("未连接，无法切换排练模式", client.log.value.last())
    }

    @Test
    fun `connect sets connecting synchronously`() {
        val client = DirectorClient()
        client.connect("127.0.0.1", 1)
        assertEquals(ConnState.CONNECTING, client.connState.value)
    }
}
