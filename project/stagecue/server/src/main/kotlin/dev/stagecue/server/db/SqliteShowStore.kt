package dev.stagecue.server.db

import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueState
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.model.Show
import org.slf4j.LoggerFactory
import java.sql.Connection
import java.sql.ResultSet
import javax.sql.DataSource

class SqliteShowStore(ds: DataSource) : AutoCloseable {

    private val log = LoggerFactory.getLogger(SqliteShowStore::class.java)
    private val lock = Any()
    private val conn: Connection = ds.connection

    init {
        conn.autoCommit = true
    }

    fun getShow(): Show = synchronized(lock) {
        val meta = readMeta()
        if (meta == null) {
            val show = defaultShow()
            writeShow(show)
            return show
        }
        val cues = readCues(meta.id)
        Show(
            id = meta.id,
            name = meta.name,
            cues = cues,
            createdAtMs = meta.createdAtMs,
            updatedAtMs = meta.updatedAtMs
        )
    }

    fun addCue(cue: Cue): Cue = synchronized(lock) {
        val exists = conn.prepareStatement("SELECT 1 FROM cue WHERE id = ?").use { ps ->
            ps.setString(1, cue.id)
            ps.executeQuery().use { rs -> rs.next() }
        }
        if (exists) throw IllegalArgumentException("cue id 已存在：${cue.id}")

        val showId = readMeta()?.id ?: defaultShow().id.also { writeShow(defaultShow()) }

        conn.prepareStatement(
            "INSERT INTO cue(id, show_id, name, type, payload, duration_ms, fade_in_ms, fade_out_ms, fallback_cue_id, notes, state, ord) " +
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ).use { ps ->
            ps.setString(1, cue.id)
            ps.setString(2, showId)
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
            ps.executeUpdate()
        }
        touchUpdatedAt()
        cue
    }

    fun updateCueState(cueId: String, state: CueState) = synchronized(lock) {
        getShow() // 语义与旧 ShowStore 一致：空库时先播种默认 show，保证 UPDATE 有行可打
        conn.prepareStatement("UPDATE cue SET state = ? WHERE id = ?").use { ps ->
            ps.setString(1, state.name)
            ps.setString(2, cueId)
            ps.executeUpdate()
        }
        touchUpdatedAt()
    }

    fun snapshotStates(): Map<String, CueState> {
        val show = getShow()
        return show.cues.associate { it.id to it.state }
    }

    override fun close() {
        synchronized(lock) {
            runCatching { conn.close() }
                .onFailure { log.warn("关闭 SQLite 连接失败：{}", it.message) }
        }
    }

    private data class Meta(val id: String, val name: String, val createdAtMs: Long, val updatedAtMs: Long)

    private fun readMeta(): Meta? {
        conn.prepareStatement(
            "SELECT id, name, created_at_ms, updated_at_ms FROM show_meta LIMIT 1"
        ).use { ps ->
            ps.executeQuery().use { rs ->
                return if (rs.next()) {
                    Meta(
                        id = rs.getString("id"),
                        name = rs.getString("name"),
                        createdAtMs = rs.getLong("created_at_ms"),
                        updatedAtMs = rs.getLong("updated_at_ms")
                    )
                } else null
            }
        }
    }

    private fun readCues(showId: String): List<Cue> {
        conn.prepareStatement(
            "SELECT id, name, type, payload, duration_ms, fade_in_ms, fade_out_ms, fallback_cue_id, notes, state, ord " +
                "FROM cue WHERE show_id = ? ORDER BY ord"
        ).use { ps ->
            ps.setString(1, showId)
            ps.executeQuery().use { rs ->
                val list = mutableListOf<Cue>()
                while (rs.next()) list += rs.toCue()
                return list
            }
        }
    }

    private fun ResultSet.toCue(): Cue {
        val type = parseEnum(getString("type"), CueType.AUDIO)
        val state = parseEnum(getString("state"), CueState.IDLE)
        return Cue(
            id = getString("id"),
            name = getString("name"),
            type = type,
            payload = getString("payload"),
            durationMs = getLong("duration_ms"),
            fadeInMs = getLong("fade_in_ms"),
            fadeOutMs = getLong("fade_out_ms"),
            fallbackCueId = getString("fallback_cue_id"),
            notes = getString("notes"),
            state = state,
            order = getInt("ord")
        )
    }

    private inline fun <reified T : Enum<T>> parseEnum(raw: String?, fallback: T): T {
        if (raw == null) return fallback
        return try {
            enumValueOf<T>(raw)
        } catch (e: IllegalArgumentException) {
            log.warn("未知枚举值 '{}'（{}），回退 {}", raw, T::class.simpleName, fallback)
            fallback
        }
    }

    private fun writeShow(show: Show) {
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
        } catch (e: Exception) {
            conn.rollback()
            log.error("写入默认 show 失败，已回滚", e)
            throw e
        } finally {
            conn.autoCommit = true
        }
    }

    private fun touchUpdatedAt() {
        conn.prepareStatement("UPDATE show_meta SET updated_at_ms = ?").use { ps ->
            ps.setLong(1, System.currentTimeMillis())
            ps.executeUpdate()
        }
    }

    private fun defaultShow(): Show = Show(
        id = "show-default",
        name = "StageCue 演示演出",
        createdAtMs = System.currentTimeMillis(),
        updatedAtMs = System.currentTimeMillis(),
        cues = listOf(
            Cue(id = "cue-001", name = "开场音乐", type = CueType.AUDIO, state = CueState.IDLE, order = 1),
            Cue(id = "cue-002", name = "追光开", type = CueType.LIGHT, state = CueState.IDLE, order = 2),
            Cue(id = "cue-003", name = "主持人字幕", type = CueType.SUBTITLE, state = CueState.IDLE, order = 3),
            Cue(id = "cue-004", name = "演员上场提示", type = CueType.PROMPT, state = CueState.IDLE, order = 4),
            Cue(id = "cue-005", name = "谢幕音乐", type = CueType.AUDIO, state = CueState.IDLE, order = 5)
        )
    )
}
