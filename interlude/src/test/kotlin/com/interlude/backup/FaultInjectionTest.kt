package com.interlude.backup

import com.interlude.runLint
import com.interlude.runRestore
import java.io.File
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.junit.jupiter.api.io.TempDir

class FaultInjectionTest {

    @Test
    fun `lint on directory returns 2`(@TempDir tempDir: File) {
        val dir = File(tempDir, "subdir")
        assertTrue(dir.mkdirs())
        assertEquals(2, runLint(arrayOf("lint", dir.absolutePath)))
    }

    @Test
    fun `lint on empty file returns 2 without crashing`(@TempDir tempDir: File) {
        val empty = File(tempDir, "empty.interlude")
        assertTrue(empty.createNewFile())
        assertEquals(2, runLint(arrayOf("lint", empty.absolutePath)))
    }

    @Test
    fun `restore throws IllegalArgumentException when backup file deleted before restore`(@TempDir tempDir: File) {
        val file = File(tempDir, "script.interlude")
        file.writeText("v1")
        val bak = BackupManager.snapshot(file)
        assertNotNull(bak)
        assertTrue(bak.delete())
        assertTrue(!bak.exists())
        assertFailsWith<IllegalArgumentException> {
            BackupManager.restore(file, 0)
        }
    }

    @Test
    fun `backup roundtrip works with spaces in filename`(@TempDir tempDir: File) {
        val file = File(tempDir, "my script 1.interlude")
        file.writeText("v1")
        val bak = BackupManager.snapshot(file)
        assertNotNull(bak)
        file.writeText("v2")
        BackupManager.restore(file, 0)
        assertEquals("v1", file.readText())
        assertEquals(2, BackupManager.listBackups(file).size)
    }

    @Test
    fun `restore with negative index returns 2`(@TempDir tempDir: File) {
        val file = File(tempDir, "script.interlude")
        file.writeText("v1")
        assertNotNull(BackupManager.snapshot(file))
        assertEquals(2, runRestore(arrayOf("restore", file.absolutePath, "--index", "-1")))
    }

    @Test
    fun `restore on missing script file returns 2`(@TempDir tempDir: File) {
        val missing = File(tempDir, "does-not-exist.interlude")
        assertTrue(!missing.exists())
        assertEquals(2, runRestore(arrayOf("restore", missing.absolutePath)))
    }

    @Test
    fun `two snapshots at same instant get unique names`(@TempDir tempDir: File) {
        val file = File(tempDir, "script.interlude")
        file.writeText("v1")
        val now = Instant.parse("2024-01-01T00:00:00Z")
        val first = BackupManager.snapshot(file, now)
        val second = BackupManager.snapshot(file, now)
        assertNotNull(first)
        assertNotNull(second)
        assertTrue(first.name != second.name)
        assertTrue(first.exists())
        assertTrue(second.exists())
        assertEquals("v1", first.readText())
        assertEquals("v1", second.readText())
    }
}
