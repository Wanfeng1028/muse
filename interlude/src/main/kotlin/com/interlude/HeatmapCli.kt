package com.interlude

import com.interlude.log.Log
import com.interlude.replay.HeatmapAnalyzer
import com.interlude.replay.HeatmapJson
import com.interlude.replay.HeatmapText
import com.interlude.replay.SessionEvent
import com.interlude.replay.SessionLog
import com.interlude.replay.SessionLogParseException
import java.io.File

/**
 * 处理 `heatmap` 子命令：读取多份对局日志，生成路径热力报告。
 *
 * @return 进程退出码，0 表示成功。
 */
fun runHeatmap(args: Array<String>): Int {
    var format = "text"
    var out: String? = null
    val positional = mutableListOf<String>()

    var i = 1
    while (i < args.size) {
        when (args[i]) {
            "--format" -> {
                if (i + 1 >= args.size) printUsageAndExit()
                val value = args[i + 1]
                if (value != "text" && value != "json") printUsageAndExit()
                format = value
                i += 2
            }
            "--log-level" -> {
                if (i + 1 >= args.size) printUsageAndExit()
                Log.setLevel(args[i + 1])
                i += 2
            }
            "--log-json" -> {
                Log.jsonMode = true
                i += 1
            }
            "--out" -> {
                if (i + 1 >= args.size) printUsageAndExit()
                out = args[i + 1]
                i += 2
            }
            else -> {
                positional.add(args[i])
                i += 1
            }
        }
    }

    if (positional.isEmpty()) printUsageAndExit()

    val sessions = mutableListOf<List<SessionEvent>>()
    for (path in positional) {
        val file = File(path)
        if (!file.exists()) {
            System.err.println("文件不存在: $path")
            return 2
        }
        val text = try {
            file.readText()
        } catch (e: Exception) {
            System.err.println("读取文件失败: $path")
            return 2
        }
        val events = try {
            SessionLog.parse(text)
        } catch (e: SessionLogParseException) {
            System.err.println("对局日志解析失败: ${e.message}")
            return 2
        }
        sessions.add(events)
    }

    val report = HeatmapAnalyzer.analyze(sessions)
    val rendered = if (format == "json") HeatmapJson.render(report) else HeatmapText.render(report)

    if (out != null) {
        try {
            File(out).writeText(rendered)
        } catch (e: Exception) {
            System.err.println("写入报告失败: $out")
            return 2
        }
    } else {
        println(rendered)
    }

    Log.info(
        "heatmap",
        "热力报告已生成",
        mapOf("sessions" to sessions.size, "choices" to report.totalChoices, "format" to format)
    )
    return 0
}
