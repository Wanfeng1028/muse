package dev.stagecue.shared.oplog

interface OpLogStore {
    fun append(type: String, cueId: String?, detail: String = ""): OpLogEntry
    fun readAll(): List<OpLogEntry>
    fun clear()
}
