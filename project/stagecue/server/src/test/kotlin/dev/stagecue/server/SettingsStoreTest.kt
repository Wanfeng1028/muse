package dev.stagecue.server.db

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.sql.SQLException

class SettingsStoreTest {

    @Test
    fun `set then get returns the same value`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            store.set("greeting", "hello world")
            assertEquals("hello world", store.get("greeting"))
        } finally {
            store.close()
        }
    }

    @Test
    fun `get of missing key returns null`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            assertNull(store.get("never-written-key"))
        } finally {
            store.close()
        }
    }

    @Test
    fun `set twice overwrites value and keeps a single row`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            store.set("dup", "first")
            store.set("dup", "second")
            assertEquals("second", store.get("dup"))

            ds.connection.use { conn ->
                conn.prepareStatement("SELECT COUNT(*) FROM settings WHERE key = ?").use { ps ->
                    ps.setString(1, "dup")
                    ps.executeQuery().use { rs ->
                        assertTrue(rs.next())
                        assertEquals(1, rs.getInt(1))
                    }
                }
            }
        } finally {
            store.close()
        }
    }

    @Test
    fun `getBoolean returns default true when key is absent`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            assertTrue(store.getBoolean("absent-true", true))
        } finally {
            store.close()
        }
    }

    @Test
    fun `getBoolean returns default false when key is absent`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            assertFalse(store.getBoolean("absent-false", false))
        } finally {
            store.close()
        }
    }

    @Test
    fun `getBoolean parses strict true`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            store.set("flag-true", "true")
            assertTrue(store.getBoolean("flag-true", false))
        } finally {
            store.close()
        }
    }

    @Test
    fun `getBoolean parses strict false`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            store.set("flag-false", "false")
            assertFalse(store.getBoolean("flag-false", true))
        } finally {
            store.close()
        }
    }

    @Test
    fun `getBoolean returns default for capitalized True`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            store.set("flag-caps", "True")
            assertFalse(store.getBoolean("flag-caps", false))
        } finally {
            store.close()
        }
    }

    @Test
    fun `getBoolean returns default for numeric one`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            store.set("flag-one", "1")
            assertTrue(store.getBoolean("flag-one", true))
        } finally {
            store.close()
        }
    }

    @Test
    fun `getBoolean returns default for empty string`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        try {
            store.set("flag-empty", "")
            assertFalse(store.getBoolean("flag-empty", false))
        } finally {
            store.close()
        }
    }

    @Test
    fun `close is idempotent and get after close throws SQLException`(@TempDir tempDir: File) {
        val ds = Database.init(tempDir)
        val store = SettingsStore(ds)
        store.close()
        store.close()

        assertThrows(SQLException::class.java) {
            store.get("after-close")
        }
    }
}
