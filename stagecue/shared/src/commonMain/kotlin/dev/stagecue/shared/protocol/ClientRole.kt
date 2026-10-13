package dev.stagecue.shared.protocol

import kotlinx.serialization.Serializable

@Serializable
enum class ClientRole {
    DIRECTOR,
    MONITOR,
    LIGHTING
}
