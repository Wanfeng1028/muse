package dev.stagecue.shared.model

import kotlinx.serialization.Serializable

@Serializable
data class Cue(
    val id: String,
    val name: String,
    val type: CueType,
    val payload: String = "",
    val durationMs: Long = 0,
    val fadeInMs: Long = 0,
    val fadeOutMs: Long = 0,
    val fallbackCueId: String? = null,
    val notes: String = "",
    val state: CueState = CueState.IDLE,
    val order: Int = 0
)
