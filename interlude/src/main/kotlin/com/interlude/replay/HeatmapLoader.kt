
package com.interlude.replay

import java.io.File

/** 对局日志目录加载状态。 */
enum class HeatmapLoadStatus {
    OK, DIR_MISSING, NO_JSON, ALL_FAILED
}

/** HeatmapLoader.load 的返回。 */
data class HeatmapLoadResult(
    val status: HeatmapLoadStatus,
    val report: HeatmapReport?,
    val failedFiles: List<String>,
    val fileCount: Int,
)

/**
 * 纯 Kotlin 的对局日志加载器（无 Compose 依赖，可直编单测）。
 * 扫描 dir 下 *.json，逐个 SessionLog.parse，失败的记入 failedFiles 并跳过；
 * 全部成功解析的文件聚合成 HeatmapAnalyzer.analyze 的输入。
 */
object HeatmapLoader {
    fun load(dir: File): HeatmapLoadResult {
        if (!dir.exists() || !dir.isDirectory) {
            return HeatmapLoadResult(HeatmapLoadStatus.DIR_MISSING, null, emptyList(), 0)
        }
        val files = dir.listFiles { f: File -> f.isFile && f.name.endsWith(".json") }
            ?.sortedBy { it.name } ?: emptyList()
        if (files.isEmpty()) {
            return HeatmapLoadResult(HeatmapLoadStatus.NO_JSON, null, emptyList(), 0)
        }
        val sessions = ArrayList<List<SessionEvent>>()
        val failures = ArrayList<String>()
        for (f in files) {
            try {
                sessions.add(SessionLog.parse(f.readText()))
            } catch (e: Exception) {
                failures.add(f.name)
            }
        }
        if (sessions.isEmpty()) {
            return HeatmapLoadResult(HeatmapLoadStatus.ALL_FAILED, null, failures, files.size)
        }
        return HeatmapLoadResult(
            HeatmapLoadStatus.OK,
            HeatmapAnalyzer.analyze(sessions),
            failures,
            files.size,
        )
    }
}
