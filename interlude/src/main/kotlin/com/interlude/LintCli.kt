package com.interlude

import com.interlude.dsl.ParseError
import com.interlude.dsl.Parser
import com.interlude.lint.Report
import com.interlude.lint.Severity
import com.interlude.lint.Validator
import com.interlude.log.Log
import java.io.File
import kotlin.system.exitProcess

private const val USAGE = """用法: interlude-lint lint <剧本文件> [--log-level LEVEL] [--log-json] [--format text|json]

选项:
  --log-level LEVEL   日志级别: trace/debug/info/warn/error (默认 info)
  --log-json          日志以 JSON 行输出到 stderr
  --format FORMAT     报告格式: text 或 json (默认 text)"""

private fun printUsageAndExit(): Nothing {
    System.err.println(USAGE)
    exitProcess(2)
}

fun main(args: Array<String>) {
    if (args.isEmpty() || args[0] != "lint") printUsageAndExit()

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
                if (value != "text" && value != "json") printUsageAndExit()
                format = value
                i += 2
            }
            else -> {
                positional.add(arg)
                i += 1
            }
        }
    }
    if (positional.size != 1) printUsageAndExit()
    val scriptPath = positional[0]

    Log.info("startup", "校验任务启动", mapOf("file" to scriptPath))

    val file = File(scriptPath)
    if (!file.exists()) {
        System.err.println("文件不存在: $scriptPath")
        printUsageAndExit()
    }

    val source = try {
        file.readText()
    } catch (e: Exception) {
        System.err.println("读取文件失败: $scriptPath")
        exitProcess(2)
    }

    val parseStart = System.currentTimeMillis()
    val story = try {
        Parser(source).parse()
    } catch (e: ParseError) {
        Log.error("parse", "解析失败", mapOf("file" to scriptPath, "line" to e.line))
        System.err.println(e.message)
        exitProcess(2)
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

    val errors = issues.count { it.severity == Severity.ERROR }
    val warnings = issues.count { it.severity == Severity.WARNING }

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

    exitProcess(if (errors > 0) 1 else 0)
}