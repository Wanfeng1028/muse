package dev.stagecue.server

import dev.stagecue.server.db.Database
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class DatabaseInitDeepTest {

    @TempDir
    lateinit var tempDir: File

    @Test
    fun `init creates data dir and db file`() {
        // 事实来源：Database.init 内 dataDir.mkdirs() + url 拼 stagecue.db
        val dataDir = File(tempDir, "fresh")
        assertFalse(dataDir.exists())
        val ds = Database.init(dataDir)
        assertTrue(dataDir.isDirectory)
        assertTrue(File(dataDir, "stagecue.db").exists())
        ds.connection.close()
    }

    @Test
    fun `init applies at least one migration on fresh dir`() {
        // 事实来源：Database.init 内 lastMigrationsApplied = migrate(ds)，源码资源含 V1__init.sql + V2__settings.sql
        val dataDir = File(tempDir, "fresh-migrate")
        val ds = Database.init(dataDir)
        assertTrue(Database.lastMigrationsApplied >= 1)
        ds.connection.close()
    }

    @Test
    fun `migrate twice is idempotent`() {
        // 事实来源：Database.migrate 返回 result.migrationsExecuted，Flyway 对已应用迁移返回 0
        val dataDir = File(tempDir, "idempotent")
        val ds = Database.init(dataDir)
        val second = Database.migrate(ds)
        assertEquals(0, second)
        ds.connection.close()
    }

    @Test
    fun `init sets journal mode to wal`() {
        // 事实来源：Database.init 内 st.execute("PRAGMA journal_mode=WAL")
        val dataDir = File(tempDir, "wal")
        val ds = Database.init(dataDir)
        val mode = ds.connection.use { conn ->
            conn.createStatement().use { st ->
                st.executeQuery("PRAGMA journal_mode").use { rs ->
                    rs.next()
                    rs.getString(1)
                }
            }
        }
        assertEquals("wal", mode.lowercase())
    }

    @Test
    fun `init enables foreign keys`() {
        // 事实来源：Database.init 内 st.execute("PRAGMA foreign_keys=ON")
        val dataDir = File(tempDir, "fk")
        val ds = Database.init(dataDir)
        val fk = ds.connection.use { conn ->
            conn.createStatement().use { st ->
                st.executeQuery("PRAGMA foreign_keys").use { rs ->
                    rs.next()
                    rs.getInt(1)
                }
            }
        }
        assertEquals(1, fk)
    }

    @Test
    fun `importJsonIfNeeded returns silently when show json missing`() {
        // 事实来源：importJsonIfNeeded 内 jsonFile.exists() 为 false 即 return
        val dataDir = File(tempDir, "no-json")
        val ds = Database.init(dataDir)
        assertFalse(File(dataDir, "show.json").exists())
        assertDoesNotThrow { Database.importJsonIfNeeded(dataDir, ds) }
        ds.connection.close()
    }
}