package com.interlude

import com.interlude.backup.BackupManager
import com.interlude.dsl.ParseError
import com.interlude.dsl.Parser
import com.interlude.lint.Report
import com.interlude.lint.Severity
import com.interlude.lint.Validator
import com.interlude.log.Log
import java.io.File
import kotlin.system.exitProcess

private const val USAGE = """用法: interlude-lint <命令> [选项]

命令:
lint <剧本文件> 校验剧本
restore <剧本文件> 列出或恢复备份

lint 选项:
--log-level LEVEL 日志级别: trace/debug/info/warn/error (默认 info)
--log-json 日志以 JSON 行输出到 stderr
--format FORMAT 报告格式: text 或 json (默认 text)

restore 选项:
--log-level LEVEL 日志级别: trace/debug/info/warn/error (默认 info)
--log-json 日志以 JSON 行输出到 stderr
--list 列出全部备份（默认行为）
--index N 恢复第 N 个备份（0=最新）"""

private fun printUsageAndExit(): Nothing {
    System.err.println(USAGE)
    exitProcess(2)
}

fun runLint(args: Array<String>): Int {
    var format = "text"
    val positional = mutableListOf<String>()

    var i = 1
    while (i < args.size) {
        when (val arg = args[i]) {
            "--log-level" -> {
                if (i + 1 >= args.size) printUsageAndExit()
                try {
                    Log.setLevel(args[i + 1])
                } catch (e: IllegalArgumentException) {
                    printUsageAndExit()
                }
                i += 2
            }
            "--log-json" -> {
                Log.jsonMode = true
                i += 1
            }
            "--format" -> {
                if (i + 1 >= args.size) printUsageAndExit()
                val value = args[i + 1]
                if (value!= "text" && value!= "json") printUsageAndExit()
                format = value
                i += 2
            }
            else -> {
                positional.add(arg)
                i += 1
            }
        }
    }
    if (positional.size!= 1) printUsageAndExit()
    val scriptPath = positional[0]

    Log.info("startup", "校验任务启动", mapOf("file" to scriptPath))

    val file = File(scriptPath)
    if (!file.exists()) {
        System.err.println("文件不存在: $scriptPath")
        printUsageAndExit()
    }

    try {
        val bak = BackupManager.snapshot(file)
        if (bak!= null) {
            Log.info("backup", "打开前已自动备份", mapOf("file" to scriptPath, "backup" to bak.name, "kept" to BackupManager.listBackups(file).size))
        }
    } catch (e: Exception) {
        Log.warn("backup", "自动备份失败", mapOf("file" to scriptPath, "error" to (e.message?: "unknown")))
    }

    val source = try {
        file.readText()
    } catch (e: Exception) {
        System.err.println("读取文件失败: $scriptPath")
        return 2
    }

    val parseStart = System.currentTimeMillis()
    val story = try {
        Parser(source).parse()
    } catch (e: ParseError) {
        Log.error("parse", "解析失败", mapOf("file" to scriptPath, "line" to e.line))
        System.err.println(e.message)
        return 2
    }
    val parseDuration = System.currentTimeMillis() - parseStart
    Log.info(
        "parse",
        "解析完成",
        mapOf(
            "file" to scriptPath,
            "scenes" to story.scenes.size,
            "durationMs" to parseDuration,
        ),
    )

    val validateStart = System.currentTimeMillis()
    val issues = Validator.validate(story)
    val validateDuration = System.currentTimeMillis() - validateStart

    val errors = issues.count { it.severity == Severity.ERROR}
    val warnings = issues.count { it.severity == Severity.WARNING}

    Log.info(
        "validate",
        "校验完成",
        mapOf(
            "scenes" to story.scenes.size,
            "issues" to issues.size,
            "errors" to errors,
            "warnings" to warnings,
            "durationMs" to validateDuration,
        ),
    )
    for (issue in issues) {
        Log.debug(
            "validate",
            "命中规则",
            mapOf("code" to issue.code, "scene" to issue.sceneId, "line" to issue.line),
        )
    }

    println(if (format == "json") Report.formatJson(issues) else Report.formatText(issues))
    Log.info("report", "报告已输出", mapOf("format" to format, "issues" to issues.size))

    return if (errors > 0) 1 else 0
}

fun runRestore(args: Array<String>): Int {
    var list = false
    var index: Int? = null
    val positional = mutableListOf<String>()

    var i = 1
    while (i < args.size) {
        when (val arg = args[i]) {
            "--log-level" -> {
                if (i + 1 >= args.size) printUsageAndExit()
                try {
                    Log.setLevel(args[i + 1])
                } catch (e: IllegalArgumentException) {
                    printUsageAndExit()
                }
                i += 2
            }
            "--log-json" -> {
                Log.jsonMode = true
                i += 1
            }
            "--list" -> {
                list = true
                i += 1
            }
            "--index" -> {
                if (i + 1 >= args.size) printUsageAndExit()
                val value = args[i + 1]
                val parsed = value.toIntOrNull()
                if (parsed == null) {
                    System.err.println(USAGE)
                    return 2
                }
                index = parsed
                i += 2
            }
            else -> {
                positional.add(arg)
                i += 1
            }
        }
    }
    if (positional.size!= 1) printUsageAndExit()
    val scriptPath = positional[0]

    Log.info("startup", "恢复任务启动", mapOf("file" to scriptPath))

    val file = File(scriptPath)
    if (!file.exists()) {
        System.err.println("文件不存在: $scriptPath")
        return 2
    }

    if (index == null) {
        val backups = BackupManager.listBackups(file)
        Log.info("restore", "列出备份", mapOf("file" to scriptPath, "count" to backups.size))
        if (backups.isEmpty()) {
            println("无可用备份: $scriptPath")
        } else {
            for ((idx, bak) in backups.withIndex()) {
                println("[$idx] ${bak.name} (${bak.length()} bytes)")
            }
        }
        return 0
    }

    val backups = BackupManager.listBackups(file)
    val target = index
    if (target !in backups.indices) {
        System.err.println("备份索引越界: $target，共 ${backups.size} 个备份")
        return 2
    }

    val restoredFrom = backups[target]
    try {
        BackupManager.restore(file, target)
    } catch (e: IllegalArgumentException) {
        System.err.println(e.message)
        return 2
    }

    println("已恢复: $scriptPath <- ${restoredFrom.name}")
    Log.info("restore", "已恢复备份", mapOf("file" to scriptPath, "from" to restoredFrom.name))
    return 0
}

fun main(args: Array<String>) {
    if (args.isEmpty()) printUsageAndExit()
    when (args[0]) {
        "lint" -> exitProcess(runLint(args))
        "restore" -> exitProcess(runRestore(args))
        else -> printUsageAndExit()
    }
}
