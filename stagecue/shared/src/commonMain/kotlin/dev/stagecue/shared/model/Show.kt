package dev.stagecue.shared.model

import kotlinx.serialization.Serializable

@Serializable
data class Show(
    val id: String,
    val name: String,
    val cues: List<Cue>,
    val createdAtMs: Long,
    val updatedAtMs: Long
)
