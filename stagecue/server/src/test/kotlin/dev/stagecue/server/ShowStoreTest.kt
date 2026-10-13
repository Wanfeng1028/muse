package dev.stagecue.server

import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.model.CueType
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class ShowStoreTest {

    @TempDir
    lateinit var tempDir: File

    @Test
    fun `default show has 5 cues`() {
        val store = ShowStore(tempDir)
        val show = store.getShow()
        assertEquals(5, show.cues.size)
        assertTrue(show.cues.any { it.name == "开场音乐" && it.type == CueType.AUDIO })
        assertTrue(show.cues.any { it.name == "追光开" && it.type == CueType.LIGHT })
        assertTrue(show.cues.any { it.name == "主持人字幕" && it.type == CueType.SUBTITLE })
        assertTrue(show.cues.any { it.name == "演员上场提示" && it.type == CueType.PROMPT })
        assertTrue(show.cues.any { it.name == "谢幕音乐" && it.type == CueType.AUDIO })
    }

    @Test
    fun `add cue persists across store reload`() {
        val store1 = ShowStore(tempDir)
        val newCue = Cue(
            id = "cue-extra",
            name = "谢幕追光",
            type = CueType.LIGHT,
            state = CueState.IDLE,
            order = 99
        )
        store1.addCue(newCue)

        val store2 = ShowStore(tempDir)
        val show = store2.getShow()
        assertEquals(6, show.cues.size)
        val found = show.cues.firstOrNull { it.id == "cue-extra" }
        assertEquals("谢幕追光", found?.name)
        assertEquals(CueType.LIGHT, found?.type)
    }

    @Test
    fun `update cue state persists`() {
        val store1 = ShowStore(tempDir)
        store1.updateCueState("cue-001", CueState.FIRING)

        val store2 = ShowStore(tempDir)
        val states = store2.snapshotStates()
        assertEquals(CueState.FIRING, states["cue-001"])
    }
}
