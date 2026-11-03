package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.model.Show
import kotlinx.serialization.json.Json
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class SqliteShowStoreTest {

    @TempDir
    lateinit var tempDir: File

    private val json = Json {
        prettyPrint = true
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    @Test
    fun `default show has 5 cues`() {
        val ds = Database.init(tempDir)
        SqliteShowStore(ds).use { store ->
            val show = store.getShow()
            assertEquals(5, show.cues.size)
            val c1 = show.cues.first { it.id == "cue-001" }
            assertEquals("开场音乐", c1.name)
            assertEquals(CueType.AUDIO, c1.type)
            val c2 = show.cues.first { it.id == "cue-002" }
            assertEquals("追光开", c2.name)
            assertEquals(CueType.LIGHT, c2.type)
            val c3 = show.cues.first { it.id == "cue-003" }
            assertEquals("主持人字幕", c3.name)
            assertEquals(CueType.SUBTITLE, c3.type)
            val c4 = show.cues.first { it.id == "cue-004" }
            assertEquals("演员上场提示", c4.name)
            assertEquals(CueType.PROMPT, c4.type)
            val c5 = show.cues.first { it.id == "cue-005" }
            assertEquals("谢幕音乐", c5.name)
            assertEquals(CueType.AUDIO, c5.type)
        }
    }

    @Test
    fun `add cue persists across store reload`() {
        val ds1 = Database.init(tempDir)
        SqliteShowStore(ds1).use { store ->
            store.addCue(
                Cue(id = "cue-006", name = "彩排提示", type = CueType.PROMPT, state = CueState.IDLE, order = 6)
            )
        }

        val ds2 = Database.init(tempDir)
        SqliteShowStore(ds2).use { store ->
            val show = store.getShow()
            assertEquals(6, show.cues.size)
            assertTrue(show.cues.any { it.id == "cue-006" })
        }
    }

    @Test
    fun `update cue state persists`() {
        val ds1 = Database.init(tempDir)
        SqliteShowStore(ds1).use { store ->
            store.updateCueState("cue-001", CueState.FIRING)
        }

        val ds2 = Database.init(tempDir)
        SqliteShowStore(ds2).use { store ->
            assertEquals(CueState.FIRING, store.snapshotStates()["cue-001"])
        }
    }

    @Test
    fun `json migration imports show json once`() {
        val show = Show(
            id = "show-import",
            name = "导入演出",
            createdAtMs = 1000L,
            updatedAtMs = 2000L,
            cues = (1..6).map { i ->
                Cue(
                    id = "imp-%03d".format(i),
                    name = "导入cue$i",
                    type = CueType.AUDIO,
                    state = CueState.IDLE,
                    order = i
                )
            }
        )
        File(tempDir, "show.json").writeText(json.encodeToString(Show.serializer(), show))

        val ds1 = Database.init(tempDir)
        SqliteShowStore(ds1).use { store ->
            assertEquals(6, store.getShow().cues.size)
        }

        val ds2 = Database.init(tempDir)
        SqliteShowStore(ds2).use { store ->
            assertEquals(6, store.getShow().cues.size)
        }
    }

    @Test
    fun `settings roundtrip`() {
        val ds = Database.init(tempDir)
        SettingsStore(ds).use { settings ->
            assertNull(settings.get("rehearsal"))
            assertFalse(settings.getBoolean("rehearsal", false))
            assertTrue(settings.getBoolean("missing", true))

            settings.set("rehearsal", "true")
            assertEquals("true", settings.get("rehearsal"))
            assertTrue(settings.getBoolean("rehearsal", false))

            settings.set("rehearsal", "false")
            assertEquals("false", settings.get("rehearsal"))
            assertFalse(settings.getBoolean("rehearsal", true))
        }
    }

    @Test
    fun `flyway migration is idempotent`() {
        val ds = Database.init(tempDir)
        val second = Database.migrate(ds)
        assertEquals(0, second)
    }
}
