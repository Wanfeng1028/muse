package dev.stagecue.shared.oplog

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class OpLogTest {

    @Test
    fun inMemoryAppendAndReadInOrder() {
        val store = InMemoryOpLogStore()
        val e1 = store.append(type = "ARM", cueId = "cue-1", detail = "armed")
        val e2 = store.append(type = "FIRE", cueId = "cue-1", detail = "fired")
        val e3 = store.append(type = "ARM", cueId = "cue-2", detail = "")

        val all = store.readAll()
        assertEquals(3, all.size)
        assertEquals(e1.seq, all[0].seq)
        assertEquals(e2.seq, all[1].seq)
        assertEquals(e3.seq, all[2].seq)
        assertEquals(1L, all[0].seq)
        assertEquals(2L, all[1].seq)
        assertEquals(3L, all[2].seq)
    }

    @Test
    fun seqIsMonotonicAfterClear() {
        val store = InMemoryOpLogStore()
        store.append(type = "A", cueId = null, detail = "")
        store.append(type = "B", cueId = null, detail = "")
        store.clear()
        val after = store.append(type = "C", cueId = null, detail = "")
        assertEquals(1L, after.seq)
        assertEquals(1, store.readAll().size)
    }

    @Test
    fun eventIdIsUnique() {
        val store = InMemoryOpLogStore()
        val ids = HashSet<String>()
        repeat(50) {
            ids.add(store.append(type = "X", cueId = null, detail = "").eventId)
        }
        assertEquals(50, ids.size)
    }

    @Test
    fun readAllReturnsCopy() {
        val store = InMemoryOpLogStore()
        store.append(type = "A", cueId = null, detail = "")
        val snapshot = store.readAll()
        store.append(type = "B", cueId = null, detail = "")
        assertEquals(1, snapshot.size)
        assertTrue(store.readAll().size == 2)
    }
}
