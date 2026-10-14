package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.shared.protocol.CueFired
import dev.stagecue.shared.protocol.RehearsalChanged
import dev.stagecue.shared.protocol.TriggerCue
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.util.UUID

class SyncHubRehearsalTest {

    @Test
    fun `rehearsal defaults to false`(@TempDir dir: File) {
        val db = Database.init(dir)
        val hub = SyncHub(settings = SettingsStore(db))
        assertFalse(hub.rehearsalMode)
    }

    @Test
    fun `setRehearsal persists across hub instances`(@TempDir dir: File) {
        val ds = Database.init(dir)
        val hub1 = SyncHub(settings = SettingsStore(ds))

        val changed = hub1.setRehearsal(true)
        assertTrue(changed is RehearsalChanged)
        assertTrue(changed.enabled)

        val hub2 = SyncHub(settings = SettingsStore(ds))
        assertTrue(hub2.rehearsalMode)

        hub2.setRehearsal(false)
        val hub3 = SyncHub(settings = SettingsStore(ds))
        assertFalse(hub3.rehearsalMode)
    }

    @Test
    fun `trigger in rehearsal mode is marked`(@TempDir dir: File) {
        val db = Database.init(dir)
        val hub = SyncHub(settings = SettingsStore(db))

        hub.setRehearsal(true)
        val fired1 = hub.handleTriggerCue(
            TriggerCue(msgId = UUID.randomUUID().toString(), sentAtMs = 1000L, cueId = "cue-001")
        )
        assertTrue(fired1 is CueFired)
        assertTrue((fired1 as CueFired).rehearsal)

        hub.setRehearsal(false)
        val fired2 = hub.handleTriggerCue(
            TriggerCue(msgId = UUID.randomUUID().toString(), sentAtMs = 2000L, cueId = "cue-001")
        )
        assertTrue(fired2 is CueFired)
        assertFalse((fired2 as CueFired).rehearsal)
    }

    @Test
    fun `rehearsal toggle without settings store stays false`() {
        val hub = SyncHub()
        // 无持久化后端时切换不应抛异常，且模式恒为 false
        hub.setRehearsal(true)
        assertFalse(hub.rehearsalMode)
    }
}
