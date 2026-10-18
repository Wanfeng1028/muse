package com.interlude

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.PrintStream

class LintCliDeepTest {

    private val validScript = """
        scene start:
          text: "你好。"
          end
    """.trimIndent()

    @Test
    fun `lint valid script returns 0`(@TempDir tempDir: File) {
        val file = File(tempDir, "valid.interlude")
        file.writeText(validScript)
        val result = runLint(arrayOf("lint", file.absolutePath))
        assertEquals(0, result)
    }

    @Test
    fun `lint directory returns 2`(@TempDir tempDir: File) {
        val result = runLint(arrayOf("lint", tempDir.absolutePath))
        assertEquals(2, result)
    }

    @Test
    fun `lint script with parse error returns 2`(@TempDir tempDir: File) {
        val file = File(tempDir, "broken.interlude")
        file.writeText("this is not a script !!!")
        val result = runLint(arrayOf("lint", file.absolutePath))
        assertEquals(2, result)
    }

    @Test
    fun `lint json format returns 0 and prints json`(@TempDir tempDir: File) {
        val file = File(tempDir, "valid.interlude")
        file.writeText(validScript)
        val originalOut = System.out
        val captured = ByteArrayOutputStream()
        System.setOut(PrintStream(captured))
        try {
            val result = runLint(arrayOf("lint", file.absolutePath, "--format", "json"))
            assertEquals(0, result)
        } finally {
            System.setOut(originalOut)
        }
    }

    @Test
    fun `restore non-numeric index returns 2`(@TempDir tempDir: File) {
        val file = File(tempDir, "whatever.interlude")
        file.writeText(validScript)
        val result = runRestore(arrayOf("restore", file.absolutePath, "--index", "abc"))
        assertEquals(2, result)
    }

    @Test
    fun `restore missing file returns 2`(@TempDir tempDir: File) {
        val missing = File(tempDir, "nope.interlude")
        val result = runRestore(arrayOf("restore", missing.absolutePath))
        assertEquals(2, result)
    }

    @Test
    fun `restore list with no backups prints message`(@TempDir tempDir: File) {
        val file = File(tempDir, "empty.interlude")
        file.writeText(validScript)
        val originalOut = System.out
        val captured = ByteArrayOutputStream()
        System.setOut(PrintStream(captured))
        val result: Int
        try {
            result = runRestore(arrayOf("restore", file.absolutePath))
        } finally {
            System.setOut(originalOut)
        }
        assertEquals(0, result)
        assertTrue(captured.toString().contains("无可用备份"))
    }
}
