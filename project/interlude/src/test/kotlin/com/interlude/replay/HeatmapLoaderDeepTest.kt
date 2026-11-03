package com.interlude.replay

import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class HeatmapLoaderDeepTest {

    private val tempRoots = ArrayList<File>()

    private fun tempDir(): File {
        val d = Files.createTempDirectory("heatmap-loader-deep").toFile()
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

    private fun validLog(vararg events: String): String {
        val eventsJson = events.joinToString(",")
        return """{"session":{"id":"s1","script":"sc","startedAt":"2026-01-01T00:00:00+08:00"},"events":[$eventsJson]}"""
    }

    private val sceneA = """{"type":"scene","scene":"a","at":"2026-01-01T00:00:01+08:00"}"""

    @Test
    fun subdirectoryJsonNotRecursed() {
        val dir = tempDir()
        val sub = File(dir, "sub")
        sub.mkdirs()
        File(sub, "a.json").writeText(validLog(sceneA))
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.NO_JSON, result.status)
        assertEquals(0, result.fileCount)
        assertTrue(result.failedFiles.isEmpty())
        assertTrue(result.report == null)
    }

    @Test
    fun pathIsRegularFileNotDirectory() {
        val root = tempDir()
        val file = File(root, "regular.json")
        file.writeText(validLog(sceneA))
        val result = HeatmapLoader.load(file)
        assertEquals(HeatmapLoadStatus.DIR_MISSING, result.status)
        assertEquals(0, result.fileCount)
        assertTrue(result.report == null)
        assertTrue(result.failedFiles.isEmpty())
    }

    @Test
    fun truncatedJsonSingleBrace() {
        val dir = tempDir()
        File(dir, "trunc.json").writeText("{")
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.ALL_FAILED, result.status)
        assertEquals(listOf("trunc.json"), result.failedFiles)
        assertEquals(1, result.fileCount)
        assertTrue(result.report == null)
    }

    @Test
    fun topLevelArrayRejected() {
        val dir = tempDir()
        File(dir, "arr.json").writeText("[1,2]")
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.ALL_FAILED, result.status)
        assertEquals(listOf("arr.json"), result.failedFiles)
        assertEquals(1, result.fileCount)
        assertTrue(result.report == null)
    }

    @Test
    fun missingSessionField() {
        val dir = tempDir()
        File(dir, "nosession.json").writeText("""{"events":[]}""")
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.ALL_FAILED, result.status)
        assertEquals(listOf("nosession.json"), result.failedFiles)
        assertEquals(1, result.fileCount)
    }

    @Test
    fun unknownEventType() {
        val dir = tempDir()
        File(dir, "warp.json").writeText(
            """{"session":{"id":"s","script":"sc","startedAt":"2026-01-01T00:00:00+08:00"},"events":[{"type":"warp","at":"2026-01-01T00:00:01+08:00"}]}"""
        )
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.ALL_FAILED, result.status)
        assertEquals(listOf("warp.json"), result.failedFiles)
        assertEquals(1, result.fileCount)
        assertTrue(result.report == null)
    }

    @Test
    fun zeroByteEmptyFile() {
        val dir = tempDir()
        File(dir, "empty.json").writeText("")
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.ALL_FAILED, result.status)
        assertEquals(listOf("empty.json"), result.failedFiles)
        assertEquals(1, result.fileCount)
        assertTrue(result.report == null)
    }

    @Test
    fun hugeLogTwentyThousandScenes() {
        val dir = tempDir()
        val sb = StringBuilder()
        sb.append("""{"session":{"id":"big","script":"sc","startedAt":"2026-01-01T00:00:00+08:00"},"events":[""")
        for (i in 0 until 20000) {
            if (i > 0) sb.append(',')
            sb.append("""{"type":"scene","scene":"n$i","at":"2026-01-01T00:00:01+08:00"}""")
        }
        sb.append("]}")
        File(dir, "big.json").writeText(sb.toString())
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.OK, result.status)
        assertEquals(1, result.fileCount)
        assertTrue(result.failedFiles.isEmpty())
        val report = assertNotNull(result.report)
        assertEquals(1, report.sessionCount)
    }

    @Test
    fun mixedTwoValidThreeBroken() {
        val dir = tempDir()
        File(dir, "a.json").writeText(validLog(sceneA))
        File(dir, "b.json").writeText(validLog(sceneA))
        File(dir, "c.json").writeText("not json")
        File(dir, "d.json").writeText("{")
        File(dir, "e.json").writeText("[1]")
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.OK, result.status)
        assertEquals(5, result.fileCount)
        assertEquals(listOf("c.json", "d.json", "e.json"), result.failedFiles)
        val report = assertNotNull(result.report)
        assertEquals(2, report.sessionCount)
    }

    @Test
    fun validLogWithEmptyEvents() {
        val dir = tempDir()
        File(dir, "empty-events.json").writeText(
            """{"session":{"id":"s","script":"sc","startedAt":"2026-01-01T00:00:00+08:00"},"events":[]}"""
        )
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.OK, result.status)
        assertEquals(1, result.fileCount)
        assertTrue(result.failedFiles.isEmpty())
        val report = assertNotNull(result.report)
        assertEquals(1, report.sessionCount)
        assertEquals(0, report.totalChoices)
    }

    @Test
    fun chineseFileNameValidLog() {
        val dir = tempDir()
        File(dir, "对局1.json").writeText(validLog(sceneA))
        val result = HeatmapLoader.load(dir)
        assertEquals(HeatmapLoadStatus.OK, result.status)
        assertEquals(1, result.fileCount)
        assertTrue(result.failedFiles.isEmpty())
        val report = assertNotNull(result.report)
        assertEquals(1, report.sessionCount)
    }
}

