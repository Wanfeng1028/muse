package dev.stagecue.server

import dev.stagecue.shared.oplog.FileOpLogStore
import dev.stagecue.shared.oplog.OpLogEntry
import dev.stagecue.shared.protocol.WsJson
import kotlinx.serialization.decodeFromString
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class FileOpLogStoreTest {

    @Test
    fun `append persists entries to disk with sequential seq`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")
        store.append("CUE_FIRED", "cue-3", "eventId=e3")

        val all = store.readAll()
        assertEquals(3, all.size)
        assertEquals(listOf(1L, 2L, 3L), all.map { it.seq })

        val file = File(dir, "oplog.jsonl")
        assertTrue(file.exists())
        val lines = file.readLines().filter { it.isNotBlank() }
        assertEquals(3, lines.size)
    }

    @Test
    fun `restart restores entries and continues seq`(@TempDir dir: File) {
        val store1 = FileOpLogStore(dir)
        store1.append("CUE_FIRED", "cue-1", "eventId=e1")
        store1.append("CUE_FIRED", "cue-2", "eventId=e2")

        val store2 = FileOpLogStore(dir)
        val restored = store2.readAll()
        assertEquals(2, restored.size)
        assertEquals(listOf(1L, 2L), restored.map { it.seq })

        val third = store2.append("CUE_FIRED", "cue-3", "eventId=e3")
        assertEquals(3L, third.seq)
        assertEquals(3, store2.readAll().size)
    }

    @Test
    fun `concurrent append yields exact seq set`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        val threads = 8
        val perThread = 25
        val total = threads * perThread
        val start = CountDownLatch(1)
        val done = CountDownLatch(threads)
        repeat(threads) { t ->
            Thread {
                start.await()
                repeat(perThread) { i ->
                    store.append("CUE_FIRED", "cue-$t-$i", "eventId=e-$t-$i")
                }
                done.countDown()
            }.start()
        }
        start.countDown()
        assertTrue(done.await(30, TimeUnit.SECONDS))

        val seqs = store.readAll().map { it.seq }.toSet()
        assertEquals((1L..total.toLong()).toSet(), seqs)
        assertEquals(total, store.readAll().size)
    }

    @Test
    fun `corrupted trailing line is skipped on load`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")

        val file = File(dir, "oplog.jsonl")
        file.appendText("{\"seq\":3,\"eventId\":\"x\"\n")

        val store2 = FileOpLogStore(dir)
        val all = store2.readAll()
        assertEquals(2, all.size)
        assertEquals(listOf(1L, 2L), all.map { it.seq })
    }

    @Test
    fun `empty directory starts empty and first append is seq 1`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        assertTrue(store.readAll().isEmpty())
        val first = store.append("CUE_FIRED", "cue-1", "eventId=e1")
        assertEquals(1L, first.seq)
    }

    @Test
    fun `clear wipes memory and file`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")

        store.clear()
        assertTrue(store.readAll().isEmpty())

        val first = store.append("CUE_FIRED", "cue-1", "eventId=e1")
        assertEquals(1L, first.seq)
    }

    @Test
    fun `missedOps returns entries after lastSeenSeq`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")
        store.append("CUE_FIRED", "cue-3", "eventId=e3")

        val hub = SyncHub(opLog = store)
        assertEquals(listOf(2L, 3L), hub.missedOps(1L).map { it.seq })
        assertTrue(hub.missedOps(3L).isEmpty())
        assertTrue(hub.missedOps(null).isEmpty())
    }

    @Test
    fun `each line decodes independently as OpLogEntry`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")

        val file = File(dir, "oplog.jsonl")
        val lines = file.readLines().filter { it.isNotBlank() }
        assertEquals(2, lines.size)
        lines.forEach { line ->
            val entry = WsJson.json.decodeFromString<OpLogEntry>(line)
            assertTrue(entry.seq >= 1L)
            assertFalse(entry.eventId.isEmpty())
        }
    }

    @Test
    fun `mid-file corrupted line is skipped and neighbors keep order`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")
        store.append("CUE_FIRED", "cue-3", "eventId=e3")

        val file = File(dir, "oplog.jsonl")
        val lines = file.readLines().filter { it.isNotBlank() }
        assertEquals(3, lines.size)
        file.writeText(lines[0] + "\n" + "THIS IS NOT JSON {{{" + "\n" + lines[1] + "\n" + lines[2] + "\n")

        val store2 = FileOpLogStore(dir)
        val all = store2.readAll()
        assertEquals(3, all.size)
        assertEquals(listOf(1L, 2L, 3L), all.map { it.seq })
        assertEquals(listOf("cue-1", "cue-2", "cue-3"), all.map { it.cueId })
    }

    @Test
    fun `fully corrupted file starts empty without throwing`(@TempDir dir: File) {
        val file = File(dir, "oplog.jsonl")
        file.writeText("not json at all\n{{{\n<<<garbage>>>\n")

        val store = FileOpLogStore(dir)
        assertTrue(store.readAll().isEmpty())

        val first = store.append("CUE_FIRED", "cue-1", "eventId=e1")
        assertEquals(1L, first.seq)
        assertEquals(1, store.readAll().size)
    }

    @Test
    fun `blank lines are ignored on load`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")

        val file = File(dir, "oplog.jsonl")
        file.appendText("\n   \n\t\n")

        val store2 = FileOpLogStore(dir)
        val all = store2.readAll()
        assertEquals(2, all.size)
        assertEquals(listOf(1L, 2L), all.map { it.seq })
        assertEquals(listOf("cue-1", "cue-2"), all.map { it.cueId })
    }

    @Test
    fun `nonexistent nested directory is created on construction`(@TempDir dir: File) {
        val nested = File(dir, "a/b")
        assertFalse(nested.exists())

        val store = FileOpLogStore(nested)
        assertTrue(nested.exists())

        val entry = store.append("CUE_FIRED", "cue-1", "eventId=e1")
        assertEquals(1L, entry.seq)
        assertTrue(File(nested, "oplog.jsonl").exists())
        assertEquals(1, store.readAll().size)
    }

    @Test
    fun `clear deletes the backing file from disk`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")

        store.clear()
        assertFalse(File(dir, "oplog.jsonl").exists())
        assertTrue(store.readAll().isEmpty())
    }

    @Test
    fun `append after clear restarts at seq 1 and old lines are gone`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")

        store.clear()
        val entry = store.append("CUE_FIRED", "cue-1", "eventId=e1")
        assertEquals(1L, entry.seq)

        val lines = File(dir, "oplog.jsonl").readLines().filter { it.isNotBlank() }
        assertEquals(1, lines.size)
        val decoded = WsJson.json.decodeFromString<OpLogEntry>(lines[0])
        assertEquals(1L, decoded.seq)
        assertEquals("cue-1", decoded.cueId)
    }

    @Test
    fun `readAll returns defensive copy`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        store.append("CUE_FIRED", "cue-1", "eventId=e1")
        store.append("CUE_FIRED", "cue-2", "eventId=e2")

        val snapshot = store.readAll() as MutableList
        assertEquals(2, snapshot.size)
        snapshot.clear()
        assertEquals(0, snapshot.size)

        val after = store.readAll()
        assertEquals(2, after.size)
        assertEquals(listOf(1L, 2L), after.map { it.seq })
    }

    @Test
    fun `utf8 detail round-trips through restart`(@TempDir dir: File) {
        val detail = "灯光 cue 触发 @ 排练模式 #3"
        val store1 = FileOpLogStore(dir)
        store1.append("CUE_FIRED", "cue-1", detail)

        val store2 = FileOpLogStore(dir)
        val all = store2.readAll()
        assertEquals(1, all.size)
        assertEquals(detail, all[0].detail)
    }

    @Test
    fun `large replay preserves exact order`(@TempDir dir: File) {
        val store1 = FileOpLogStore(dir)
        repeat(500) { i ->
            store1.append("CUE_FIRED", "cue-$i", "eventId=e-$i")
        }

        val store2 = FileOpLogStore(dir)
        val all = store2.readAll()
        assertEquals(500, all.size)
        assertEquals((1L..500L).toList(), all.map { it.seq })
        assertEquals("cue-0", all.first().cueId)
        assertEquals("cue-499", all.last().cueId)
    }

    @Test
    fun `eventIds are unique across appends`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        repeat(100) { i ->
            store.append("CUE_FIRED", "cue-$i", "eventId=e-$i")
        }

        val all = store.readAll()
        assertEquals(100, all.size)
        assertEquals(100, all.map { it.eventId }.toSet().size)
    }

    @Test
    fun `concurrent append and readAll never throws`(@TempDir dir: File) {
        val store = FileOpLogStore(dir)
        val writers = 4
        val perWriter = 50
        val total = writers * perWriter
        val readers = 2
        val readsPerReader = 100
        val start = CountDownLatch(1)
        val done = CountDownLatch(writers + readers)
        val readErrors = arrayOfNulls<Throwable>(1)
        val lock = Any()

        repeat(writers) { w ->
            Thread {
                start.await()
                try {
                    repeat(perWriter) { i ->
                        store.append("CUE_FIRED", "cue-$w-$i", "eventId=e-$w-$i")
                    }
                } catch (t: Throwable) {
                    synchronized(lock) {
                        if (readErrors[0] == null) readErrors[0] = t
                    }
                } finally {
                    done.countDown()
                }
            }.start()
        }

        repeat(readers) {
            Thread {
                start.await()
                try {
                    repeat(readsPerReader) {
                        val snapshot = store.readAll()
                        assertTrue(snapshot.size >= 0)
                    }
                } catch (t: Throwable) {
                    synchronized(lock) {
                        if (readErrors[0] == null) readErrors[0] = t
                    }
                } finally {
                    done.countDown()
                }
            }.start()
        }

        start.countDown()
        assertTrue(done.await(60, TimeUnit.SECONDS))

        synchronized(lock) {
            assertEquals(null, readErrors[0])
        }

        val all = store.readAll()
        assertEquals(total, all.size)
        assertEquals((1L..total.toLong()).toSet(), all.map { it.seq }.toSet())
    }

    @Test
    fun `all fields survive restart`(@TempDir dir: File) {
        val store1 = FileOpLogStore(dir)
        val appended = store1.append("CUE_FIRED", "cue-9", "d9")
        val eventId = appended.eventId
        val atMs = appended.atMs

        val store2 = FileOpLogStore(dir)
        val all = store2.readAll()
        assertEquals(1, all.size)
        val restored = all[0]
        assertEquals(appended.seq, restored.seq)
        assertEquals("CUE_FIRED", restored.type)
        assertEquals("cue-9", restored.cueId)
        assertEquals("d9", restored.detail)
        assertEquals(eventId, restored.eventId)
        assertEquals(atMs, restored.atMs)
    }
}
