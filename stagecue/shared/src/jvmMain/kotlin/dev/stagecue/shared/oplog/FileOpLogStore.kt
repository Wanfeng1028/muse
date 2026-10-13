package dev.stagecue.shared.oplog

import dev.stagecue.shared.protocol.WsJson
import kotlinx.serialization.encodeToString
import java.io.File
import java.util.UUID

/**
 * JSON Lines backed op log. Each line is one serialized [OpLogEntry].
 * On construction, existing lines are loaded so that [seq] continues monotonically.
 */
class FileOpLogStore(private val dir: File) : OpLogStore {

    private val file: File = File(dir, "oplog.jsonl").also { dir.mkdirs() }

    private val entries = ArrayList<OpLogEntry>()
    private var nextSeq: Long = 1
    private val lock = Any()

    init {
        synchronized(lock) {
            if (file.exists()) {
                file.forEachLine { line ->
                    val trimmed = line.trim()
                    if (trimmed.isNotEmpty()) {
                        val entry = WsJson.json.decodeFromString<OpLogEntry>(trimmed)
                        entries.add(entry)
                    }
                }
            }
            nextSeq = (entries.maxOfOrNull { it.seq } ?: 0L) + 1L
        }
    }

    override fun append(type: String, cueId: String?, detail: String): OpLogEntry {
        synchronized(lock) {
            val entry = OpLogEntry(
                seq = nextSeq,
                eventId = UUID.randomUUID().toString(),
                type = type,
                cueId = cueId,
                atMs = System.currentTimeMillis(),
                detail = detail
            )
            nextSeq += 1
            entries.add(entry)
            file.appendText(WsJson.json.encodeToString(entry) + "\n")
            return entry
        }
    }

    override fun readAll(): List<OpLogEntry> = synchronized(lock) { ArrayList(entries) }

    override fun clear() {
        synchronized(lock) {
            entries.clear()
            nextSeq = 1
            if (file.exists()) file.delete()
        }
    }
}
