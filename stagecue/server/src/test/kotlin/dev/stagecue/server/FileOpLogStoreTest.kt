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
}
