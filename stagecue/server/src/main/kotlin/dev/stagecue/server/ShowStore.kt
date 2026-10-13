package dev.stagecue.server

import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.model.Show
import kotlinx.serialization.json.Json
import org.slf4j.LoggerFactory
import java.io.File

class ShowStore(private val dataDir: File) {

    private val log = LoggerFactory.getLogger(ShowStore::class.java)
    private val json = Json {
        prettyPrint = true
        ignoreUnknownKeys = true
        encodeDefaults = true
    }
    private val showFile = File(dataDir, "show.json")
    private val lock = Any()

    @Volatile
    private var cached: Show? = null

    init {
        if (!dataDir.exists()) dataDir.mkdirs()
    }

    fun getShow(): Show {
        cached?.let { return it }
        synchronized(lock) {
            cached?.let { return it }
            val loaded = if (showFile.exists()) {
                runCatching { json.decodeFromString<Show>(showFile.readText()) }
                    .onFailure { log.warn("Failed to load show.json, creating default: {}", it.message) }
                    .getOrNull()
            } else null

            val show = loaded ?: defaultShow().also { saveLocked(it) }
            cached = show
            return show
        }
    }

    fun addCue(cue: Cue): Cue {
        synchronized(lock) {
            val current = cached ?: loadOrCreateLocked()
            val updated = current.copy(cues = current.cues + cue)
            saveLocked(updated)
            cached = updated
            return cue
        }
    }

    fun updateCueState(cueId: String, state: CueState) {
        synchronized(lock) {
            val current = cached ?: loadOrCreateLocked()
            val updatedCues = current.cues.map { cue ->
                if (cue.id == cueId) cue.copy(state = state) else cue
            }
            val updated = current.copy(cues = updatedCues)
            saveLocked(updated)
            cached = updated
        }
    }

    fun snapshotStates(): Map<String, CueState> {
        val current = getShow()
        return current.cues.associate { it.id to it.state }
    }

    private fun loadOrCreateLocked(): Show {
        val loaded = if (showFile.exists()) {
            runCatching { json.decodeFromString<Show>(showFile.readText()) }.getOrNull()
        } else null
        return loaded ?: defaultShow()
    }

    private fun saveLocked(show: Show) {
        val tmp = File(dataDir, "show.json.tmp")
        tmp.writeText(json.encodeToString(Show.serializer(), show))
        if (showFile.exists()) showFile.delete()
        if (!tmp.renameTo(showFile)) {
            // Fallback: copy then delete
            tmp.copyTo(showFile, overwrite = true)
            tmp.delete()
        }
    }

    private fun defaultShow(): Show = Show(
        id = "show-default",
        name = "StageCue 演示演出",
        createdAtMs = System.currentTimeMillis(),
        updatedAtMs = System.currentTimeMillis(),
        cues = listOf(
            Cue(
                id = "cue-001",
                name = "开场音乐",
                type = CueType.AUDIO,
                state = CueState.IDLE,
                order = 1
            ),
            Cue(
                id = "cue-002",
                name = "追光开",
                type = CueType.LIGHT,
                state = CueState.IDLE,
                order = 2
            ),
            Cue(
                id = "cue-003",
                name = "主持人字幕",
                type = CueType.SUBTITLE,
                state = CueState.IDLE,
                order = 3
            ),
            Cue(
                id = "cue-004",
                name = "演员上场提示",
                type = CueType.PROMPT,
                state = CueState.IDLE,
                order = 4
            ),
            Cue(
                id = "cue-005",
                name = "谢幕音乐",
                type = CueType.AUDIO,
                state = CueState.IDLE,
                order = 5
            )
        )
    )
}
