package com.interlude

import com.interlude.log.Log
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class HeatmapCliDeepTest {

    @TempDir
    lateinit var dir: File

    private val validLog = """
        {
          "session": { "id": "demo-001", "script": "sample.interlude", "players": 1, "startedAt": "2026-10-16T20:00:00+08:00" },
          "events": [
            { "type": "scene", "scene": "prologue", "at": "2026-10-16T20:00:05+08:00" },
            { "type": "choice", "scene": "prologue", "label": "走向候车室", "target": "hall",
              "alternatives": [ { "label": "留在站台", "target": "platform" } ], "at": "2026-10-16T20:00:40+08:00" },
            { "type": "scene", "scene": "hall", "at": "2026-10-16T20:00:41+08:00" }
          ]
        }
    """.trimIndent()

    private val emptyEventsLog = """
        {
          "session": { "id": "empty-001", "script": "sample.interlude", "players": 1, "startedAt": "2026-10-16T20:00:00+08:00" },
          "events": []
        }
    """.trimIndent()

    private fun writeLog(name: String, content: String): File {
        val f = File(dir, name)
        f.writeText(content)
        return f
    }

    @AfterEach
    fun restoreLogLevel() {
        Log.setLevel("info")
        Log.jsonMode = false
    }

    // 事实来源：!file.exists() 分支 System.err 打印 "文件不存在" 并 return 2
    @Test
    fun missingLogFileReturns2() {
        val code = runHeatmap(arrayOf("heatmap", File(dir, "nope.json").absolutePath))
        assertEquals(2, code)
    }

    // 事实来源：SessionLog.parse 抛 SessionLogParseException 分支 return 2
    @Test
    fun invalidLogContentReturns2() {
        val f = writeLog("bad.json", "this is not json")
        val code = runHeatmap(arrayOf("heatmap", f.absolutePath))
        assertEquals(2, code)
    }

    // 事实来源：末尾 return 0（合法单日志 text 格式）
    @Test
    fun validSingleLogTextReturns0() {
        val f = writeLog("s1.json", validLog)
        val code = runHeatmap(arrayOf("heatmap", f.absolutePath))
        assertEquals(0, code)
    }

    // 事实来源：末尾 return 0（--format json 分支）
    @Test
    fun validSingleLogJsonFormatReturns0() {
        val f = writeLog("s1.json", validLog)
        val code = runHeatmap(arrayOf("heatmap", "--format", "json", f.absolutePath))
        assertEquals(0, code)
    }

    // 事实来源：File(out).writeText(rendered) 分支，输出文件存在且内容非空
    @Test
    fun outFlagWritesNonEmptyFileAndReturns0() {
        val f = writeLog("s1.json", validLog)
        val out = File(dir, "report.txt")
        val code = runHeatmap(arrayOf("heatmap", "--out", out.absolutePath, f.absolutePath))
        assertEquals(0, code)
        assertTrue(out.exists())
        assertTrue(out.readText().isNotEmpty())
    }

    // 事实来源：sessions 列表可加多个位置参数日志文件
    @Test
    fun twoValidLogsMergedReturns0() {
        val f1 = writeLog("s1.json", validLog)
        val f2 = writeLog("s2.json", emptyEventsLog)
        val code = runHeatmap(arrayOf("heatmap", f1.absolutePath, f2.absolutePath))
        assertEquals(0, code)
    }

    // 事实来源：--log-json 分支 Log.jsonMode = true，返回 0 且不抛异常
    @Test
    fun logJsonFlagReturns0() {
        val f = writeLog("s1.json", validLog)
        val code = runHeatmap(arrayOf("heatmap", "--log-json", f.absolutePath))
        assertEquals(0, code)
        assertTrue(Log.jsonMode)
    }

    // 事实来源：--log-level 分支调用 Log.setLevel，返回 0
    @Test
    fun logLevelWarnFlagReturns0() {
        val f = writeLog("s1.json", validLog)
        val code = runHeatmap(arrayOf("heatmap", "--log-level", "warn", f.absolutePath))
        assertEquals(0, code)
        assertFalse(false)
    }
}
