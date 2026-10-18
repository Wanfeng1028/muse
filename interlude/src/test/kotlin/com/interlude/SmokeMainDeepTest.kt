package com.interlude

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.ByteArrayOutputStream
import java.io.PrintStream

class SmokeMainDeepTest {

    private fun runMainCapture(): String {
        val originalOut = System.out
        val buffer = ByteArrayOutputStream()
        try {
            System.setOut(PrintStream(buffer, true, "UTF-8"))
            main()
        } finally {
            System.setOut(originalOut)
        }
        return buffer.toString("UTF-8")
    }

    @Test
    fun `main prints scene count line`() {
        val output = runMainCapture()
        assertTrue(output.contains("场景数:"), "stdout should contain scene count line")
        val match = Regex("场景数: (\\d+)").find(output)
        assertTrue(match != null, "scene count line should match expected pattern")
        val count = match!!.groupValues[1].toInt()
        assertTrue(count > 0, "parsed sample.interlude should contain at least one scene, got $count")
    }

    @Test
    fun `main prints issue count line`() {
        val output = runMainCapture()
        assertTrue(output.contains("问题数:"), "stdout should contain issue count line")
        assertTrue(Regex("问题数: (\\d+)").containsMatchIn(output), "issue count line should match expected pattern")
    }

    @Test
    fun `main prints each issue in bracket format`() {
        val output = runMainCapture()
        val countMatch = Regex("问题数: (\\d+)").find(output)
        assertTrue(countMatch != null, "issue count line should be present")
        val issueCount = countMatch!!.groupValues[1].toInt()
        if (issueCount == 0) {
            return
        }
        val issueLineRegex = Regex("^\\[(ERROR|WARNING)] \\S+ \\S+:\\d+ .+")
        val issueLines = output.lines().filter { line ->
            line.startsWith("[") && (line.contains("[ERROR]") || line.contains("[WARNING]"))
        }
        assertEquals(issueCount, issueLines.size, "each reported issue should be printed on its own line")
        issueLines.forEach { line ->
            assertTrue(
                issueLineRegex.matches(line),
                "issue line should match bracket format but was: $line"
            )
        }
        assertFalse(issueLines.isEmpty(), "issue lines should not be empty when issueCount > 0")
    }

    @Test
    fun `main does not throw`() {
        val originalOut = System.out
        val buffer = ByteArrayOutputStream()
        try {
            System.setOut(PrintStream(buffer, true, "UTF-8"))
            main()
        } finally {
            System.setOut(originalOut)
        }
        assertTrue(buffer.toString("UTF-8").isNotEmpty(), "main should produce output on stdout")
    }
}
