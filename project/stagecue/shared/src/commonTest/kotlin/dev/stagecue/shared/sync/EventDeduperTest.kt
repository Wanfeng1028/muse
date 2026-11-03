package dev.stagecue.shared.sync

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class EventDeduperTest {

    @Test
    fun firstSeenIsNew() {
        val deduper = EventDeduper()
        assertTrue(deduper.isNew("evt-1"))
        assertTrue(deduper.isNew("evt-2"))
        assertTrue(deduper.isNew("evt-3"))
    }

    @Test
    fun duplicatesReturnFalse() {
        val deduper = EventDeduper()
        assertTrue(deduper.isNew("evt-1"))
        assertFalse(deduper.isNew("evt-1"))
        assertFalse(deduper.isNew("evt-1"))
    }

    @Test
    fun slidingWindowEvictsOldest() {
        val deduper = EventDeduper(capacity = 3)
        assertTrue(deduper.isNew("a"))
        assertTrue(deduper.isNew("b"))
        assertTrue(deduper.isNew("c"))
        assertTrue(deduper.isNew("d")) // evicts "a"
        assertFalse(deduper.isNew("b")) // still remembered
        assertFalse(deduper.isNew("c")) // still remembered
        assertFalse(deduper.isNew("d")) // still remembered
        assertTrue(deduper.isNew("a")) // "a" was evicted, new again
    }
}
