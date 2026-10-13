package dev.stagecue.shared.oplog

import kotlinx.serialization.Serializable

@Serializable
data class OpLogEntry(
    val seq: Long,
    val eventId: String,
    val type: String,
    val cueId: String?,
    val atMs: Long,
    val detail: String = ""
)
