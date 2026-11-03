package com.interlude.replay

import com.interlude.runReplay
import org.junit.jupiter.api.io.TempDir
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ReplayCliTest {

    private val sampleJson = """
        {
          "session": { "id": "demo-001", "script": "sample.interlude", "players": 1, "startedAt": "2026-10-16T20:00:00+08:00" },
          "events": [
            { "type": "scene", "scene": "prologue", "at": "2026-10-16T20:00:05+08:00" },
            { "type": "choice", "scene": "prologue", "label": "走向候车室", "target": "hall",
              "alternatives": [ { "label": "留在站台", "target": "platform" } ], "at": "2026-10-16T20:00:40+08:00" },
            { "type": "scene", "scene": "hall", "at": "2026-10-16T20:00:41+08:00" },
            { "type": "note", "note": "关键抉择：推门离开需要 has_key，当时没有钥匙，只能搭话", "scene": "hall", "at": "2026-10-16T20:01:10+08:00" },
            { "type": "choice", "scene": "hall", "label": "和陌生人搭话", "target": "stranger",
              "alternatives": [ { "label": "推门离开", "target": "exit" } ], "at": "2026-10-16T20:01:30+08:00" },
            { "type": "scene", "scene": "stranger", "at": "2026-10-16T20:01:31+08:00" },
            { "type": "choice", "scene": "stranger", "label": "报上姓名", "target": "ending_a",
              "alternatives": [ { "label": "沉默", "target": "ending_b" } ], "at": "2026-10-16T20:02:00+08:00" },
            { "type": "scene", "scene": "ending_a", "at": "2026-10-16T20:02:01+08:00" },
            { "type": "end", "outcome": "抵达 ending_a：陌生人说出了你的名字", "winner": null, "at": "2026-10-16T20:02:10+08:00" }
          ]
        }
    """.trimIndent()

    @Test
    fun runReplayWithOutFileSucceeds(@TempDir dir: File) {
        val log = File(dir, "log.json")
        log.writeText(sampleJson)
        val out = File(dir, "report.md")
        val code = runReplay(arrayOf("replay", log.absolutePath, "--out", out.absolutePath))
        assertEquals(0, code)
        val md = out.readText()
        assertTrue(md.contains("# 复盘报告"))
        assertTrue(md.contains("没走的路"))
    }

    @Test
    fun runReplayWithScriptEnrichesSceneLine(@TempDir dir: File) {
        val log = File(dir, "log.json")
        log.writeText(sampleJson)
        val script = File(dir, "sample.interlude")
        script.writeText(
            """
            scene prologue:
              text: "雨。"
              choice "走" -> hall
            scene hall:
              text: "厅。"
              end
            """.trimIndent()
        )
        val out = File(dir, "report.md")
        val code = runReplay(
            arrayOf("replay", log.absolutePath, "--script", script.absolutePath, "--out", out.absolutePath)
        )
        assertEquals(0, code)
        val md = out.readText()
        assertTrue(md.contains("## 抉择点复盘"))
        assertTrue(md.contains("（第 1 行）"))
        assertTrue(md.contains("厅。"))
    }

    @Test
    fun missingLogFileReturns2(@TempDir dir: File) {
        val missing = File(dir, "nope.json")
        val code = runReplay(arrayOf("replay", missing.absolutePath))
        assertEquals(2, code)
    }

    @Test
    fun invalidJsonReturns2(@TempDir dir: File) {
        val log = File(dir, "bad.json")
        log.writeText("{ this is not json")
        val code = runReplay(arrayOf("replay", log.absolutePath))
        assertEquals(2, code)
    }

    @Test
    fun runReplayWithoutScriptReturns0(@TempDir dir: File) {
        val log = File(dir, "log.json")
        log.writeText(sampleJson)
        val code = runReplay(arrayOf("replay", log.absolutePath))
        assertEquals(0, code)
    }

    @Test
    fun missingScriptFileReturns2(@TempDir dir: File) {
        val log = File(dir, "log.json")
        log.writeText(sampleJson)
        val missingScript = File(dir, "nope.interlude")
        val code = runReplay(arrayOf("replay", log.absolutePath, "--script", missingScript.absolutePath))
        assertEquals(2, code)
    }
}
