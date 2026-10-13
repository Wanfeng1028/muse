package dev.stagecue.shared.model

import kotlinx.serialization.Serializable

@Serializable
enum class CueType {
    AUDIO,
    LIGHT,
    SUBTITLE,
    PROMPT
}
