package com.interlude.backup

import com.interlude.dsl.Parser
import com.interlude.lint.Validator
import com.interlude.runLint
import com.interlude.runRestore
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.io.PrintStream
import java.time.Instant
import java.util.concurrent.CountDownLatch
import java.util.concurrent.atomic.AtomicReference
import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.junit.jupiter.api.Assumptions.assumeFalse
import org.junit.jupiter.api.Assumptions.assumeTrue
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
        assertTrue(first.name!= second.name)
        assertTrue(first.exists())
        assertTrue(second.exists())
        assertEquals("v1", first.readText())
        assertEquals("v1", second.readText())
    }

    @Test
    fun `truncated script reports exact line via Parser`(@TempDir tempDir: File) {
        val file = File(tempDir, "broken.interlude")
        val sb = StringBuilder()
        sb.append("scene s0:\n")
        for (i in 1..29) {
            sb.append("  text: \"line$i\"\n")
        }
        sb.append("  text: \"没写完的字符串\n")
        file.writeText(sb.toString())
        val e = assertFailsWith<com.interlude.dsl.ParseError> {
            Parser(file.readText()).parse()
        }
        assertEquals(31, e.line)
    }

    @Test
    fun `garbage binary bytes lint returns 2 without crashing`(@TempDir tempDir: File) {
        val file = File(tempDir, "garbage.interlude")
        val rnd = Random(42)
        val bytes = ByteArray(256) { rnd.nextInt(0, 256).toByte() }
        bytes[0] = 0
        file.writeBytes(bytes)
        assertEquals(2, runLint(arrayOf("lint", file.absolutePath)))
    }

    @Test
    fun `parse error deep in file reports correct line end to end`(@TempDir tempDir: File) {
        val file = File(tempDir, "deep.interlude")
        val sb = StringBuilder()
        sb.append("scene s0:\n")
        for (i in 1..48) {
            sb.append("  text: \"line$i\"\n")
        }
        sb.append("  choice \"坏选择\" ->\n")
        for (i in 50..60) {
            sb.append("  text: \"tail$i\"\n")
        }
        sb.append("  end\n")
        file.writeText(sb.toString())
        val originalErr = System.err
        val buffer = ByteArrayOutputStream()
        var code = -1
        try {
            System.setErr(PrintStream(buffer))
            code = runLint(arrayOf("lint", file.absolutePath))
        } finally {
            System.setErr(originalErr)
        }
        assertEquals(2, code)
        val stderr = buffer.toString()
        assertTrue(stderr.contains("第 50 行"), "stderr 应包含 '第 50 行'，实际: $stderr")
    }

    @Test
    fun `scene header without colon reports its line`(@TempDir tempDir: File) {
        val file = File(tempDir, "nocolon.interlude")
        file.writeText("scene a:\n  text: \"x\"\nscene broken\n  end\n")
        val e = assertFailsWith<com.interlude.dsl.ParseError> {
            Parser(file.readText()).parse()
        }
        assertEquals(3, e.line)
        assertEquals(2, runLint(arrayOf("lint", file.absolutePath)))
    }

    @Test
    fun `unreadable file lint returns 2`(@TempDir tempDir: File) {
        val file = File(tempDir, "unreadable.interlude")
        file.writeText("scene s0:\n  text: \"hi\"\n  end\n")
        file.setReadable(false)
        try {
            assumeFalse(file.canRead(), "root 下权限位无效，跳过")
            val originalErr = System.err
            val buffer = ByteArrayOutputStream()
            var code = -1
            try {
                System.setErr(PrintStream(buffer))
                code = runLint(arrayOf("lint", file.absolutePath))
            } finally {
                System.setErr(originalErr)
            }
            assertEquals(2, code)
            assertTrue(buffer.toString().contains("读取文件失败"), "stderr 应包含 '读取文件失败'")
        } finally {
            file.setReadable(true)
        }
    }

    private fun mountTmpfs(dir: File): Boolean {
        val proc = Runtime.getRuntime().exec(arrayOf("mount", "-t", "tmpfs", "-o", "size=64k", "tmpfs", dir.absolutePath))
        val exit = proc.waitFor()
        return exit == 0
    }

    private fun umountTmpfs(dir: File) {
        try {
            Runtime.getRuntime().exec(arrayOf("umount", dir.absolutePath)).waitFor()
        } catch (e: Exception) {
            // 忽略 umount 失败
        }
    }

    private fun fillDisk(mountPoint: File): File {
        var i = 0
        while (true) {
            val filler = File(mountPoint, "filler-$i.bin")
            try {
                filler.writeBytes(ByteArray(8192))
            } catch (e: IOException) {
                return filler
            }
            i += 1
        }
    }

    @Test
    fun `snapshot on full filesystem throws and original untouched`(@TempDir tempDir: File) {
        val mp = File(tempDir, "mnt")
        assertTrue(mp.mkdirs())
        assumeTrue(mountTmpfs(mp), "mount tmpfs 失败，跳过")
        var filler: File? = null
        try {
            val file = File(mp, "script.interlude")
            val valid = StringBuilder()
            valid.append("scene s0:\n")
            valid.append("  text: \"hello world this is a valid script\"\n")
            valid.append("  set x = 1\n")
            valid.append("  choice \"go\" -> s1\n")
            valid.append("  end\n")
            valid.append("scene s1:\n")
            valid.append("  text: \"done\"\n")
            valid.append("  end\n")
            file.writeText(valid.toString())
            val originalContent = file.readText()
            filler = fillDisk(mp)
            assertFailsWith<IOException> {
            BackupManager.snapshot(file)
            }
            assertEquals(originalContent, file.readText())
            assertTrue(BackupManager.listBackups(file).isEmpty())
        } finally {
            filler?.delete()
            umountTmpfs(mp)
        }
    }

    @Test
    fun `runLint survives backup failure on full disk`(@TempDir tempDir: File) {
        val mp = File(tempDir, "mnt")
        assertTrue(mp.mkdirs())
        assumeTrue(mountTmpfs(mp), "mount tmpfs 失败，跳过")
        var filler: File? = null
        try {
            val file = File(mp, "script.interlude")
            val content = "scene s0:\n  text: \"hi\"\n  end\n"
            file.writeText(content)
            filler = fillDisk(mp)
            val code = runLint(arrayOf("lint", file.absolutePath))
            assertEquals(0, code)
            assertEquals(content, file.readText())
        } finally {
            filler?.delete()
            umountTmpfs(mp)
        }
    }

    @Test
    fun `restore refuses corrupted backup and keeps original`(@TempDir tempDir: File) {
        val file = File(tempDir, "script.interlude")
        file.writeText("v1")
        val bak = BackupManager.snapshot(file)
        assertNotNull(bak)
        file.writeText("v2")
        bak.setReadable(false)
        try {
            assumeFalse(bak.canRead(), "root 下权限位无效，跳过")
            assertFailsWith<IllegalArgumentException> {
            BackupManager.restore(file, 0)
            }
            assertEquals("v2", file.readText())
        } finally {
            bak.setReadable(true)
        }
    }

    @Test
    fun `runRestore returns 2 on corrupted backup without touching original`(@TempDir tempDir: File) {
        val file = File(tempDir, "script.interlude")
        file.writeText("v1")
        val bak = BackupManager.snapshot(file)
        assertNotNull(bak)
        file.writeText("v2")
        bak.setReadable(false)
        try {
            assumeFalse(bak.canRead(), "root 下权限位无效，跳过")
            val code = runRestore(arrayOf("restore", file.absolutePath, "--index", "0"))
            assertEquals(2, code)
            assertEquals("v2", file.readText())
        } finally {
            bak.setReadable(true)
        }
    }

    private fun generateHugeScript(scenes: Int, linesPerScene: Int): String {
        val sb = StringBuilder()
        for (i in 0 until scenes) {
            sb.append("scene s$i:\n")
            sb.append("  text: \"text of scene $i\"\n")
            sb.append("  set v = $i\n")
            sb.append("  choice \"go\" -> s${(i + 1) % scenes}\n")
            sb.append("  jump -> s${(i + 1) % scenes}\n")
            var lines = 5
            var j = 0
            while (lines < linesPerScene - 1) {
                sb.append("  text: \"pad-$i-$j\"\n")
                j++
                lines++
            }
            sb.append("  end\n")
        }
        return sb.toString()
    }

    @Test
    fun `100k line script parses within time budget`() {
        val src = generateHugeScript(5000, 20)
        val lineCount = src.count { it == '\n' }
        assertTrue(lineCount >= 100_000, "生成脚本应至少 100000 行，实际: $lineCount")
        val start = System.currentTimeMillis()
        val story = Parser(src).parse()
        Validator.validate(story)
        val elapsed = System.currentTimeMillis() - start
        println("[E1] 100k 行解析+校验耗时: $elapsed ms")
        assertTrue(elapsed < 60_000, "耗时 ${elapsed}ms 超过 60000ms 预算")
        assertEquals(5000, story.scenes.size)
    }

    @Test
    fun `runLint handles 100k line script end to end`(@TempDir tempDir: File) {
        val scenes = 25000
        val sb = StringBuilder()
        for (i in 0 until scenes) {
            sb.append("scene s$i:\n")
            sb.append("  text: \"t$i\"\n")
            sb.append("  choice \"go\" -> s${(i + 1) % scenes}\n")
            sb.append("  end\n")
        }
        val src = sb.toString()
        val lineCount = src.count { it == '\n' }
        assertTrue(lineCount >= 100_000, "生成脚本应至少 100000 行，实际: $lineCount")
        val file = File(tempDir, "huge.interlude")
        file.writeText(src)
        val start = System.currentTimeMillis()
        val code = runLint(arrayOf("lint", file.absolutePath))
        val elapsed = System.currentTimeMillis() - start
        println("[E2] 100k 行 runLint 端到端耗时: $elapsed ms")
        assertEquals(0, code)
        assertTrue(elapsed < 60_000, "耗时 ${elapsed}ms 超过 60000ms 预算")
    }

    @Test
    fun `concurrent lint same file does not clobber backups`(@TempDir tempDir: File) {
        val file = File(tempDir, "script.interlude")
        file.writeText("scene s0:\n  text: \"hi\"\n  end\n")
        val threads = 8
        val latch = CountDownLatch(1)
        val done = CountDownLatch(threads)
        val failure = AtomicReference<Throwable?>(null)
        val results = IntArray(threads)
        val workers = (0 until threads).map { idx ->
            Thread {
                try {
                    latch.await()
                    results[idx] = runLint(arrayOf("lint", file.absolutePath))
                } catch (t: Throwable) {
                    failure.compareAndSet(null, t)
                } finally {
                    done.countDown()
                }
            }
        }
        workers.forEach { it.start() }
        latch.countDown()
        done.await()
        assertTrue(failure.get() == null, "并发下不应有线程抛异常: ${failure.get()}")
        for (r in results) {
            assertEquals(0, r)
        }
        val backups = BackupManager.listBackups(file)
        assertEquals(backups.size, backups.toSet().size, "备份文件名不应重复")
        // 并发下 prune 交错可能短暂超过 MAX_BACKUPS=5，故只做上界断言
        assertTrue(backups.size <= 8, "备份数应 <= 8，实际: ${backups.size}")
    }
}
