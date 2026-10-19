package dev.stagecue.server

import dev.stagecue.server.db.Database
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertDoesNotThrow
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import javax.sql.DataSource

class DatabaseJsonImportDeepTest {

    private fun writeShowJson(dir: File, content: String) {
        File(dir, "show.json").writeText(content)
    }

    private fun countCue(ds: javax.sql.DataSource): Long {
        return ds.connection.use { conn ->
            conn.prepareStatement("SELECT COUNT(*) FROM cue").use { st ->
                st.executeQuery().use { rs ->
                    rs.next()
                    rs.getLong(1)
                }
            }
        }
    }

    private fun countShowMeta(ds: javax.sql.DataSource): Long {
        return ds.connection.use { conn ->
            conn.prepareStatement("SELECT COUNT(*) FROM show_meta").use { st ->
                st.executeQuery().use { rs ->
                    rs.next()
                    rs.getLong(1)
                }
            }
        }
    }

    private fun showMetaId(ds: javax.sql.DataSource): String? {
        return ds.connection.use { conn ->
            conn.prepareStatement("SELECT id FROM show_meta").use { st ->
                st.executeQuery().use { rs ->
                    if (rs.next()) rs.getString(1) else null
                }
            }
        }
    }

    private fun cueRow(ds: javax.sql.DataSource, id: String): Triple<String, String, String>? {
        return ds.connection.use { conn ->
            conn.prepareStatement("SELECT name, type, state FROM cue WHERE id = ?").use { st ->
                st.setString(1, id)
                st.executeQuery().use { rs ->
                    if (rs.next()) Triple(rs.getString(1), rs.getString(2), rs.getString(3)) else null
                }
            }
        }
    }

    // 事实来源：importJsonIfNeeded 中 jsonFile.exists() 为 false 即 return，不导入任何数据。
    @Test
    fun noShowJsonFileLeavesCueEmpty(@TempDir tmp: File) = runBlocking {
        val dataDir = File(tmp, "data1")
        dataDir.mkdirs()
        val ds = Database.init(dataDir)
        try {
            assertEquals(0L, countCue(ds))
        } finally {
        }
    }

    // 事实来源：runCatching 解析失败 -> getOrNull() ?: return，非法 JSON 不抛异常且表为空。
    @Test
    fun invalidJsonIsSkippedWithoutThrowing(@TempDir tmp: File) = runBlocking {
        val dataDir = File(tmp, "data2")
        dataDir.mkdirs()
        writeShowJson(dataDir, "{ not json")
        assertDoesNotThrow {
            runBlocking {
                val ds = Database.init(dataDir)
                try {
                    assertEquals(0L, countCue(ds))
                } finally {
                }
            }
        }
    }

    // 事实来源：show.cues 为空时 batch 为空但 show_meta 照常插入 1 条。
    @Test
    fun validJsonWithEmptyCuesInsertsShowMetaOnly(@TempDir tmp: File) = runBlocking {
        val dataDir = File(tmp, "data3")
        dataDir.mkdirs()
        val json = """
            {
              "id": "show-empty",
              "name": "空演出",
              "cues": [],
              "createdAtMs": 1000,
              "updatedAtMs": 2000
            }
        """.trimIndent()
        writeShowJson(dataDir, json)
        val ds = Database.init(dataDir)
        try {
            assertEquals(1L, countShowMeta(ds))
            assertEquals("show-empty", showMetaId(ds))
            assertEquals(0L, countCue(ds))
        } finally {
        }
    }

    // 事实来源：合法 show.json 且 cue 表为空时，cue 表插入全部 cue，type 存枚举名，state 存 "IDLE"。
    @Test
    fun validJsonWithTwoCuesImportsBothCues(@TempDir tmp: File) = runBlocking {
        val dataDir = File(tmp, "data4")
        dataDir.mkdirs()
        val json = """
            {
              "id": "show-1",
              "name": "测试演出",
              "cues": [
                {"id": "cue-1", "name": "开场音乐", "type": "AUDIO", "payload": "", "durationMs": 60000, "fadeInMs": 1000, "fadeOutMs": 2000, "fallbackCueId": null, "notes": "", "state": "IDLE", "order": 0},
                {"id": "cue-2", "name": "追光", "type": "LIGHT", "payload": "ch1=255", "durationMs": 0, "fadeInMs": 0, "fadeOutMs": 0, "fallbackCueId": null, "notes": "备注", "state": "IDLE", "order": 1}
              ],
              "createdAtMs": 1000,
              "updatedAtMs": 2000
            }
        """.trimIndent()
        writeShowJson(dataDir, json)
        val ds = Database.init(dataDir)
        try {
            assertEquals(2L, countCue(ds))
            val cue1 = cueRow(ds, "cue-1")
            assertNotNull(cue1)
            assertEquals("开场音乐", cue1!!.first)
            assertEquals("AUDIO", cue1.second)
            assertEquals("IDLE", cue1.third)
            val cue2 = cueRow(ds, "cue-2")
            assertNotNull(cue2)
            assertEquals("追光", cue2!!.first)
            assertEquals("LIGHT", cue2.second)
            assertEquals("IDLE", cue2.third)
        } finally {
        }
    }

    // 事实来源：count > 0L 即 return，已有数据时不重复导入，COUNT 保持原值。
    @Test
    fun existingCueDataPreventsReimport(@TempDir tmp: File) = runBlocking {
        val dataDir = File(tmp, "data5")
        dataDir.mkdirs()
        val ds = Database.init(dataDir)
        try {
            val conn = ds.connection
            conn.use { c ->
                c.prepareStatement(
                    "INSERT INTO show_meta(id, name, created_at_ms, updated_at_ms) VALUES ('show-x', '已有演出', 0, 0)"
                ).use { it.executeUpdate() }
                c.prepareStatement(
                    "INSERT INTO cue (id, show_id, name, type, payload, duration_ms, fade_in_ms, fade_out_ms, fallback_cue_id, notes, state, ord) " +
                        "VALUES ('existing-1', 'show-x', '已有', 'AUDIO', '', 0, 0, 0, NULL, '', 'IDLE', 0)"
                ).use { it.executeUpdate() }
            }
            assertEquals(1L, countCue(ds))

            val json = """
                {
                  "id": "show-1",
                  "name": "测试演出",
                  "cues": [
                    {"id": "cue-1", "name": "开场音乐", "type": "AUDIO", "payload": "", "durationMs": 60000, "fadeInMs": 1000, "fadeOutMs": 2000, "fallbackCueId": null, "notes": "", "state": "IDLE", "order": 0}
                  ],
                  "createdAtMs": 1000,
                  "updatedAtMs": 2000
                }
            """.trimIndent()
            writeShowJson(dataDir, json)

            Database.importJsonIfNeeded(dataDir, ds)

            assertEquals(1L, countCue(ds))
            assertNotNull(cueRow(ds, "existing-1"))
            assertEquals(null, cueRow(ds, "cue-1"))
        } finally {
        }
    }

    // 事实来源：ignoreUnknownKeys=true 但 cues 无默认值，decodeFromString 抛 MissingFieldException 被 runCatching 接住跳过。
    @Test
    fun missingCuesFieldIsSkippedWithoutThrowing(@TempDir tmp: File) = runBlocking {
        val dataDir = File(tmp, "data6")
        dataDir.mkdirs()
        val json = """
            {
              "id": "show-1",
              "name": "缺字段",
              "createdAtMs": 1000,
              "updatedAtMs": 2000
            }
        """.trimIndent()
        writeShowJson(dataDir, json)
        val ds = Database.init(dataDir)
        try {
            assertEquals(0L, countCue(ds))
        } finally {
        }
    }
}