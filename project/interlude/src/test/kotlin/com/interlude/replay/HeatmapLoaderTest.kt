
package com.interlude.replay

import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class HeatmapLoaderTest {

    private val tempRoots = ArrayList<File>()

    private fun tempDir(): File {
        val d = Files.createTempDirectory("heatmap-loader-test").toFile()
        tempRoots.add(d)
        return d
    }

    @AfterTest
    fun cleanup() {
        for (d in tempRoots) {
            d.deleteRecursively()
        }
        tempRoots.clear()
    }

    @Test
    fun dirMissing() {
        val root = tempDir()
        val missing = File(root, "不存在-xyz")
        val result = HeatmapLoader.load(missing)
        assertEquals(HeatmapLoadStatus.DIR_MISSING, result.status)
        assertTrue(result.report == null)
        assertTrue(result.failedFiles.isEmpty())
    }

    @Test
    fun noJson() {
        val dir = tempDir()
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.NO_JSON, result.status)
        assertTrue(result.report == null)
        assertTrue(result.failedFiles.isEmpty())
    }

    @Test
    fun allFailed() {
        val dir = tempDir()
        File(dir, "broken.json").writeText("not json at all")
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.ALL_FAILED, result.status)
        assertTrue(result.report == null)
        assertEquals(listOf("broken.json"), result.failedFiles)
        assertEquals(1, result.fileCount)
    }

    @Test
    fun okMixed() {
        val dir = tempDir()
        File(dir, "ok1.json").writeText(
            """{"session":{"id":"t1","script":"s","startedAt":"2026-01-01T00:00:00+08:00"},"events":[{"type":"scene","scene":"p","at":"2026-01-01T00:00:01+08:00"},{"type":"choice","scene":"p","label":"走","target":"h","at":"2026-01-01T00:00:02+08:00"},{"type":"scene","scene":"h","at":"2026-01-01T00:00:03+08:00"}]}"""
        )
        File(dir, "bad.json").writeText("{")
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.OK, result.status)
        assertEquals(2, result.fileCount)
        assertEquals(listOf("bad.json"), result.failedFiles)
        val report = assertNotNull(result.report)
        assertEquals(1, report.sessionCount)
        assertEquals(1, report.totalChoices)
        val node = report.nodes.firstOrNull { it.nodeId == "p::走" }
        assertNotNull(node)
        assertEquals(1, node.visits)
    }

    @Test
    fun nonJsonFilesIgnored() {
        val dir = tempDir()
        File(dir, "ok1.json").writeText(
        """{"session":{"id":"t1","script":"s","startedAt":"2026-01-01T00:00:00+08:00"},"events":[{"type":"scene","scene":"p","at":"2026-01-01T00:00:01+08:00"}]}"""
        )
        File(dir, "notes.txt").writeText("这不是日志")
        File(dir, "data.JSON").writeText("not json")
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.OK, result.status)
        assertEquals(1, result.fileCount)
        assertTrue(result.failedFiles.isEmpty())
        val report = assertNotNull(result.report)
        assertEquals(1, report.sessionCount)
    }
}

