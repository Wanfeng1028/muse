package dev.stagecue.shared.sync

/**
 * Sliding-window idempotency guard. Remembers the most recent [capacity] event ids.
 */
class EventDeduper(private val capacity: Int = 1000) {

    private val window = ArrayDeque<String>()
    private val seen = HashSet<String>()

    @Synchronized
    fun isNew(eventId: String): Boolean {
        if (seen.contains(eventId)) return false
        seen.add(eventId)
        window.addLast(eventId)
        while (window.size > capacity) {
            val evicted = window.removeFirst()
            seen.remove(evicted)
        }
        return true
    }

    @Synchronized
    fun size(): Int = seen.size

    @Synchronized
    fun clear() {
        window.clear()
        seen.clear()
    }
}
