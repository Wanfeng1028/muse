package com.interlude.backup

import com.interlude.log.Log
import com.interlude.runLint
import com.interlude.runRestore
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.PrintStream
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.junit.jupiter.api.io.TempDir

class BackupTest {

    private val tsRegex = Regex("""script\.interlude\.bak\.\d{8}-\d{9}""")

    @Test
    fun `snapshot creates timestamped backup with identical content`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("v1")

        val bak = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:00Z"))
        assertNotNull(bak)
        assertTrue(tsRegex.containsMatchIn(bak.name))
        assertEquals("v1", bak.readText())
    }

    @Test
    fun `snapshot returns null for missing file`(@TempDir dir: File) {
        val file = File(dir, "missing.interlude")
        assertNull(BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:00Z")))
    }

    @Test
    fun `snapshot keeps only five newest and deletes oldest`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("v0")

        val created = mutableListOf<File>()
        for (s in 0..6) {
            val now = Instant.parse("2026-10-16T04:00:0${s}Z")
            val bak = BackupManager.snapshot(file, now)
            assertNotNull(bak)
            created.add(bak)
        }

        val listed = BackupManager.listBackups(file)
        assertEquals(5, listed.size)
        assertTrue(!created[0].exists())
        assertTrue(!created[1].exists())
        for (idx in 2..6) {
            assertTrue(created[idx].exists())
        }
    }

    @Test
    fun `listBackups orders newest first`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("v0")

        val first = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:00Z"))
        val second = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:01Z"))
        val third = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:02Z"))
        assertNotNull(first)
        assertNotNull(second)
        assertNotNull(third)

        val listed = BackupManager.listBackups(file)
        assertEquals(third.name, listed[0].name)
        assertEquals(second.name, listed[1].name)
        assertEquals(first.name, listed[2].name)
    }

    @Test
    fun `restore writes backup content back to work file`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("v1")
        val bak = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:00Z"))
        assertNotNull(bak)

        file.writeText("v2")
        BackupManager.restore(file, 0, Instant.parse("2026-10-16T05:00:00Z"))
        assertEquals("v1", file.readText())
    }

    @Test
    fun `restore snapshots current work file before restoring`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("v1")
        val bak = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:00Z"))
        assertNotNull(bak)

        file.writeText("v2")
        BackupManager.restore(file, 0, Instant.parse("2026-10-16T05:00:00Z"))

        val listed = BackupManager.listBackups(file)
        assertEquals(2, listed.size)
        val hasV2 = listed.any { it.readText() == "v2" }
        assertTrue(hasV2)
    }

    @Test
    fun `restore throws on out-of-range index`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("v1")

        assertFailsWith<IllegalArgumentException> {
            BackupManager.restore(file, 0, Instant.parse("2026-10-16T04:00:00Z"))
        }

        val bak = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:00Z"))
        assertNotNull(bak)
        assertFailsWith<IllegalArgumentException> {
            BackupManager.restore(file, 5, Instant.parse("2026-10-16T05:00:00Z"))
        }
    }

    @Test
    fun `runLint logs backup op to stderr`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("scene start:\n  text: \"hello\"\n  end\n")

        val oldLevel = Log.level
        val oldJson = Log.jsonMode
        val oldErr = System.err
        val captured = ByteArrayOutputStream()
        try {
            Log.setLevel("info")
            Log.jsonMode = false
            System.setErr(PrintStream(captured, true, "UTF-8"))

            val code = runLint(arrayOf("lint", file.absolutePath))
            assertEquals(0, code)
        } finally {
            System.setErr(oldErr)
            Log.level = oldLevel
            Log.jsonMode = oldJson
        }

        assertTrue(captured.toString("UTF-8").contains("op=backup"))
    }

    @Test
    fun `runRestore list logs restore op`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("scene start:\n  text: \"hello\"\n  end\n")
        val bak = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:00Z"))
        assertNotNull(bak)

        val oldLevel = Log.level
        val oldJson = Log.jsonMode
        val oldErr = System.err
        val captured = ByteArrayOutputStream()
        val code: Int
        try {
            Log.setLevel("info")
            Log.jsonMode = false
            System.setErr(PrintStream(captured, true, "UTF-8"))
            code = runRestore(arrayOf("restore", file.absolutePath, "--list"))
        } finally {
            System.setErr(oldErr)
            Log.level = oldLevel
            Log.jsonMode = oldJson
        }

        assertEquals(0, code)
        assertTrue(captured.toString("UTF-8").contains("op=restore"))
    }

    @Test
    fun `runRestore index out of range returns 2`(@TempDir dir: File) {
        val file = File(dir, "script.interlude")
        file.writeText("scene start:\n  text: \"hello\"\n  end\n")
        val bak = BackupManager.snapshot(file, Instant.parse("2026-10-16T04:00:00Z"))
        assertNotNull(bak)

        val code = runRestore(arrayOf("restore", file.absolutePath, "--index", "7"))
        assertEquals(2, code)
    }
}
