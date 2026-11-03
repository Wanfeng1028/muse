package dev.stagecue.shared.oplog

import dev.stagecue.shared.protocol.WsJson
import kotlinx.serialization.encodeToString
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

/**
 * JSON Lines backed op log. Each line is one serialized [OpLogEntry].
 * On construction, existing lines are loaded so that [seq] continues monotonically.
 *
 * 持久化采用 append + flush + fsync，保证崩溃时已 append 的完整行不丢失；
 * 启动加载时单行解析失败仅告警并跳过，避免崩溃产生的截断尾行拖垮启动。
 */
class FileOpLogStore(private val dir: File) : OpLogStore {

    private val file: File = File(dir, "oplog.jsonl").also { dir.mkdirs() }

    private val entries = ArrayList<OpLogEntry>()
    private var nextSeq: Long = 1
    private val lock = Any()

    init {
        synchronized(lock) {
            if (file.exists()) {
                var lineNo = 0
                file.forEachLine { line ->
                    lineNo += 1
                    val trimmed = line.trim()
                    if (trimmed.isNotEmpty()) {
                        try {
                            val entry = WsJson.json.decodeFromString<OpLogEntry>(trimmed)
                            entries.add(entry)
                        } catch (e: Exception) {
                            System.err.println(
                                "FileOpLogStore: 跳过损坏行 ${file.path}:$lineNo (${e.message})"
                            )
                        }
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
            val bytes = (WsJson.json.encodeToString(entry) + "\n").toByteArray(Charsets.UTF_8)
            val out = FileOutputStream(file, true)
            try {
                out.write(bytes)
                out.flush()
                out.fd.sync()
            } finally {
                out.close()
            }
            return entry
        }
    }

    override fun readAll(): List<OpLogEntry> = synchronized(lock) { ArrayList(entries) }

    override fun clear() {
        synchronized(lock) {
            if (file.exists() && !file.delete()) {
                throw IllegalStateException("FileOpLogStore: 无法删除日志文件 ${file.path}，clear 未完成")
            }
            entries.clear()
            nextSeq = 1
        }
    }
}
