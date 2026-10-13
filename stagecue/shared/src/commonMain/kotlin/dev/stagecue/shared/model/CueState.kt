package dev.stagecue.shared.model

import kotlinx.serialization.Serializable

@Serializable
enum class CueState {
    IDLE,
    ARMED,
    FIRING,
    DONE,
    FAILED
}
