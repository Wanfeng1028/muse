package dev.stagecue.server.db

import org.slf4j.LoggerFactory
import java.sql.Connection
import javax.sql.DataSource

class SettingsStore(ds: DataSource) : AutoCloseable {

    private val log = LoggerFactory.getLogger(SettingsStore::class.java)
    private val lock = Any()
    private val conn: Connection = ds.connection

    init {
        conn.autoCommit = true
    }

    fun get(key: String): String? = synchronized(lock) {
        conn.prepareStatement("SELECT value FROM settings WHERE key = ?").use { ps ->
            ps.setString(1, key)
            ps.executeQuery().use { rs -> if (rs.next()) rs.getString(1) else null }
        }
    }

    fun set(key: String, value: String) = synchronized(lock) {
        conn.prepareStatement(
            "INSERT INTO settings(key, value) VALUES(?, ?) " +
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        ).use { ps ->
            ps.setString(1, key)
            ps.setString(2, value)
            ps.executeUpdate()
        }
        Unit
    }

    fun getBoolean(key: String, default: Boolean): Boolean {
        val raw = get(key) ?: return default
        return raw.toBooleanStrictOrNull() ?: default
    }

    override fun close() {
        synchronized(lock) {
            runCatching { conn.close() }
                .onFailure { log.warn("关闭 SettingsStore 连接失败：{}", it.message) }
        }
    }
}
