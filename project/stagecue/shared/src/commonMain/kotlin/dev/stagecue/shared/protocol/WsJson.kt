package dev.stagecue.shared.protocol

import kotlinx.serialization.json.Json

object WsJson {
    val json: Json = Json {
        ignoreUnknownKeys = true
        classDiscriminator = "kind"
        encodeDefaults = true
        isLenient = false
        explicitNulls = false
    }
}
