package dev.stagecue.server.db

import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.model.Show
import kotlinx.serialization.json.Json
import org.flywaydb.core.Flyway
import org.slf4j.LoggerFactory
import org.sqlite.SQLiteDataSource
import java.io.File
import javax.sql.DataSource

object Database {

    private val log = LoggerFactory.getLogger(Database::class.java)

    private val json = Json {
        prettyPrint = true
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** 最近一次 init 执行的迁移数，供 /metrics 的 gauge 用 */
    var lastMigrationsApplied: Int = 0
        private set

    fun init(dataDir: File): DataSource {
        if (!dataDir.exists()) dataDir.mkdirs()
        val dbFile = File(dataDir, "stagecue.db")
        // pragma 必须走 JDBC URL 参数：PRAGMA 是 per-connection 的，
        // 在单个连接上 execute 只对该连接生效，连接池的新连接拿不到。
        // URL 参数让 sqlite-jdbc 为每个新连接自动应用这些 pragma。
        val ds = SQLiteDataSource().apply {
            url = "jdbc:sqlite:${dbFile.absolutePath}?journal_mode=WAL&busy_timeout=5000&foreign_keys=ON"
        }
        lastMigrationsApplied = migrate(ds)
        importJsonIfNeeded(dataDir, ds)
        return ds
    }

    fun migrate(ds: DataSource): Int {
        val result = Flyway.configure()
            .dataSource(ds)
            .locations("classpath:db/migration")
            .load()
            .migrate()
        log.info("Flyway migrate 完成，执行了 {} 个迁移", result.migrationsExecuted)
        return result.migrationsExecuted
    }

    fun importJsonIfNeeded(dataDir: File, ds: DataSource) {
        val jsonFile = File(dataDir, "show.json")
        if (!jsonFile.exists()) return

        ds.connection.use { conn ->
            val count = conn.prepareStatement("SELECT COUNT(*) FROM cue").use { ps ->
                ps.executeQuery().use { rs ->
                    if (rs.next()) rs.getLong(1) else 0L
                }
            }
            if (count > 0L) return

            val show = runCatching { json.decodeFromString<Show>(jsonFile.readText()) }
                .onFailure { log.warn("show.json 解析失败，跳过导入：{}", it.message) }
                .getOrNull() ?: return

            conn.autoCommit = false
            try {
                conn.prepareStatement(
                    "INSERT INTO show_meta(id, name, created_at_ms, updated_at_ms) VALUES(?, ?, ?, ?)"
                ).use { ps ->
                    ps.setString(1, show.id)
                    ps.setString(2, show.name)
                    ps.setLong(3, show.createdAtMs)
                    ps.setLong(4, show.updatedAtMs)
                    ps.executeUpdate()
                }
                conn.prepareStatement(
                    "INSERT INTO cue(id, show_id, name, type, payload, duration_ms, fade_in_ms, fade_out_ms, fallback_cue_id, notes, state, ord) " +
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ).use { ps ->
                    for (cue in show.cues) {
                        ps.setString(1, cue.id)
                        ps.setString(2, show.id)
                        ps.setString(3, cue.name)
                        ps.setString(4, cue.type.name)
                        ps.setString(5, cue.payload)
                        ps.setLong(6, cue.durationMs)
                        ps.setLong(7, cue.fadeInMs)
                        ps.setLong(8, cue.fadeOutMs)
                        ps.setString(9, cue.fallbackCueId)
                        ps.setString(10, cue.notes)
                        ps.setString(11, cue.state.name)
                        ps.setInt(12, cue.order)
                        ps.addBatch()
                    }
                    ps.executeBatch()
                }
                conn.commit()
                log.info("已从 show.json 导入 {} 条 cue", show.cues.size)
            } catch (e: Exception) {
                conn.rollback()
                log.error("show.json 导入失败，已回滚", e)
                throw e
            } finally {
                conn.autoCommit = true
            }
        }
    }
}
