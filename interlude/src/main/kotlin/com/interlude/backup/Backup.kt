package com.interlude.backup

import java.io.File
import java.time.Clock
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

object BackupManager {
    const val MAX_BACKUPS: Int = 5

    private val TS_FMT: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyyMMdd-HHmmssSSS").withZone(ZoneId.systemDefault())

    /** 打开/保存前给 file 做快照。file 不存在返回 null。成功返回备份文件。 */
    fun snapshot(file: File, now: Instant = Clock.systemUTC().instant()): File? {
        if (!file.exists()) return null
        val dir = file.parentFile ?: File(".")
        val baseName = file.name + ".bak." + TS_FMT.format(now)
        var candidate = File(dir, baseName)
        var suffix = 1
        while (candidate.exists()) {
            candidate = File(dir, "$baseName-$suffix")
            suffix += 1
        }
        try {
            file.copyTo(candidate, overwrite = false)
        } catch (e: Exception) {
            // 拷贝失败（如磁盘满）不留下残留空文件，原子性语义：要么完整备份，要么没有
            candidate.delete()
            throw e
        }
        prune(file)
        return candidate
    }

    /** 列出 file 的全部备份，最新在前。 */
    fun listBackups(file: File): List<File> {
        val dir = file.parentFile ?: File(".")
        val prefix = file.name + ".bak."
        val all = dir.listFiles() ?: return emptyList()
        return all
            .filter { it.isFile && it.name.startsWith(prefix) }
            .sortedByDescending { it.name }
    }

    /**
     * 把第 index 个备份（0=最新）恢复到 file。
     * 恢复前先对当前 file 做 snapshot（file 不存在则跳过）。
     * index 越界抛 IllegalArgumentException。成功返回 file。
     */
    fun restore(file: File, index: Int, now: Instant = Clock.systemUTC().instant()): File {
        val backups = listBackups(file)
        if (index !in backups.indices) throw IllegalArgumentException("备份索引越界: $index，共 ${backups.size} 个备份")
        val content = try {
            backups[index].readBytes()
        } catch (e: Exception) {
            throw IllegalArgumentException("备份文件损坏，拒绝恢复: ${backups[index].name}")
        }
        snapshot(file, now)
        file.writeBytes(content)
        return file
    }

    private fun prune(file: File) {
        val backups = listBackups(file)
        if (backups.size <= MAX_BACKUPS) return
        for (old in backups.drop(MAX_BACKUPS)) {
            try {
                old.delete()
            } catch (e: Exception) {
                // 淘汰失败不抛出，交由上层容错
            }
        }
    }
}
