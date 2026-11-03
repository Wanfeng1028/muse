package dev.stagecue.shared.oplog

import kotlin.time.Clock
import kotlin.time.ExperimentalTime
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

@OptIn(ExperimentalUuidApi::class, ExperimentalTime::class)
class InMemoryOpLogStore : OpLogStore {

    private val entries = ArrayList<OpLogEntry>()
    private var nextSeq: Long = 1

    @Synchronized
    override fun append(type: String, cueId: String?, detail: String): OpLogEntry {
        val entry = OpLogEntry(
            seq = nextSeq,
            eventId = Uuid.random().toString(),
            type = type,
            cueId = cueId,
            atMs = Clock.System.now().toEpochMilliseconds(),
            detail = detail
        )
        nextSeq += 1
        entries.add(entry)
        return entry
    }

    @Synchronized
    override fun readAll(): List<OpLogEntry> = ArrayList(entries)

    @Synchronized
    override fun clear() {
        entries.clear()
        nextSeq = 1
    }
}
