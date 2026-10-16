package com.interlude.replay

import com.interlude.runHeatmap
import org.junit.jupiter.api.io.TempDir
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class HeatmapTextTest {

    @Test
    fun `empty report renders without throwing and contains no-data text`() {
        val report = HeatmapReport(0, 0, emptyList(), emptyList(), emptyList())
        val text = HeatmapText.render(report)
        assertTrue(text.contains("暂无数据"))
    }

    @Test
    fun `single path report contains top paths section and arrow`() {
        val node = HeatNode("a::x", "a", "x", 3, 0, 0.0)
        val hotPath = HotPath(listOf("a::x", "b::y"), 2)
        val report = HeatmapReport(1, 2, listOf(node), emptyList(), listOf(hotPath))
        val text = HeatmapText.render(report)
        assertTrue(text.contains("Top 热门路径"))
        assertTrue(text.contains(" → "))
    }

    @Test
    fun `loop data node appears in node heat table`() {
        val node = HeatNode("loop::back", "loop", "back", 2, 0, 0.0)
        val report = HeatmapReport(1, 2, listOf(node), emptyList(), emptyList())
        val text = HeatmapText.render(report)
        assertTrue(text.contains("节点热力全表"))
        assertTrue(text.contains("loop::back"))
    }

    @Test
    fun `high churn node appears in churn section with percent sign`() {
        val node = HeatNode("hall::leave", "hall", "leave", 4, 3, 0.75)
        val report = HeatmapReport(1, 4, listOf(node), listOf(node), emptyList())
        val text = HeatmapText.render(report)
        assertTrue(text.contains("Top 流失点"))
        assertTrue(text.contains("hall::leave"))
        assertTrue(text.contains("%"))
    }

    @Test
    fun `empty churn points renders threshold message`() {
        val report = HeatmapReport(1, 1, emptyList(), emptyList(), emptyList())
        val text = HeatmapText.render(report)
        assertTrue(text.contains("暂无达到阈值的流失点"))
    }

    @Test
    fun `cli writes report to out file`(@TempDir dir: File) {
        val log = File(dir, "session.json")
        log.writeText(
            """{"session": {"id":"t1","script":"s","players":1,"startedAt":"2026-10-16T20:00:00+08:00"},"events": [{"type":"scene","scene":"a","at":"2026-10-16T20:00:05+08:00"},{"type":"choice","scene":"a","label":"走","target":"b","at":"2026-10-16T20:00:06+08:00"},{"type":"scene","scene":"b","at":"2026-10-16T20:00:07+08:00"}]}"""
        )
        val out = File(dir, "report.txt")
        val code = runHeatmap(arrayOf("heatmap", log.absolutePath, "--out", out.absolutePath))
        assertEquals(0, code)
        assertTrue(out.readText().contains("路径热力报告"))
    }

    @Test
    fun `cli json format output contains node_id`(@TempDir dir: File) {
        val log = File(dir, "session.json")
        log.writeText(
            """{"session": {"id":"t1","script":"s","players":1,"startedAt":"2026-10-16T20:00:00+08:00"},"events": [{"type":"scene","scene":"a","at":"2026-10-16T20:00:05+08:00"},{"type":"choice","scene":"a","label":"走","target":"b","at":"2026-10-16T20:00:06+08:00"},{"type":"scene","scene":"b","at":"2026-10-16T20:00:07+08:00"}]}"""
        )
        val out = File(dir, "report.json")
        val code = runHeatmap(
            arrayOf("heatmap", log.absolutePath, "--format", "json", "--out", out.absolutePath)
        )
        assertEquals(0, code)
        assertTrue(out.readText().contains("\"node_id\""))
    }

    @Test
    fun `cli missing log file returns 2`(@TempDir dir: File) {
        val missing = File(dir, "nope.json")
        val code = runHeatmap(arrayOf("heatmap", missing.absolutePath))
        assertEquals(2, code)
    }
}
