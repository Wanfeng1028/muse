package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.model.MonitorState
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.server.testing.testApplication
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.boolean
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * GET /api/monitor 端点契约的集成测试（以 MonitorApiTest 已验证用法为准）。
 *
 * - ds = Database.init(tempDir)；store = SqliteShowStore(ds)；settings = SettingsStore(ds)
 * - hub = SyncHub(clock = { fixedNow })；testApplication { application { module(store, hub, settings) } }
 * - JSON 结构断言走 Json { ignoreUnknownKeys = true } 解码，不依赖 prettyPrint 空格
 */
class MonitorApiDeepTest {

    private val json = Json { ignoreUnknownKeys = true }

    private fun setup(tempDir: File, fixedNow: Long): Triple<SqliteShowStore, SyncHub, SettingsStore> {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(clock = { fixedNow })
        return Triple(store, hub, settings)
    }

    @Test
    fun `空库时返回默认快照且字段齐全`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val (store, hub, settings) = setup(tempDir, fixedNow)
        application { module(store, hub, settings) }

        val response = client.get("/api/monitor")
        assertEquals(HttpStatusCode.OK, response.status)

        val m: MonitorState = json.decodeFromString(response.bodyAsText())
        assertEquals(fixedNow, m.serverTimeMs, "serverTimeMs 应精确等于注入时钟")
        assertNull(m.next, "空库 next 应为 null")
        assertEquals(false, m.rehearsal, "空库 rehearsal 应为 false")
        assertTrue(m.serverTimeMs > 0, "serverTimeMs 应为正数")
    }

    @Test
    fun `固定时钟下 serverTimeMs 精确等于注入值`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_234_567_890_123L
        val (store, hub, settings) = setup(tempDir, fixedNow)
        application { module(store, hub, settings) }

        val m: MonitorState = json.decodeFromString(client.get("/api/monitor").bodyAsText())
        assertEquals(fixedNow, m.serverTimeMs)
    }

    @Test
    fun `有 cue 时 next 指向 order 最小的 cue`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val (store, hub, settings) = setup(tempDir, fixedNow)
        store.addCue(Cue(id = "cue-002", name = "第二", type = CueType.AUDIO, durationMs = 60000, order = 2))
        store.addCue(Cue(id = "cue-001", name = "开场", type = CueType.AUDIO, durationMs = 60000, order = 1))
        application { module(store, hub, settings) }

        val m: MonitorState = json.decodeFromString(client.get("/api/monitor").bodyAsText())
        assertEquals("cue-001", m.next?.id, "next 应为 order 最小的 cue-001")
    }

    @Test
    fun `响应 Content-Type 为 application-json`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val (store, hub, settings) = setup(tempDir, fixedNow)
        application { module(store, hub, settings) }

        val response = client.get("/api/monitor")
        assertEquals(HttpStatusCode.OK, response.status)
        assertTrue(
            response.contentType()?.match(ContentType.Application.Json) == true,
            "Content-Type 应为 application/json，实际=${response.contentType()}"
        )
    }

    @Test
    fun `未知字段容忍解码不抛错`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val (store, hub, settings) = setup(tempDir, fixedNow)
        application { module(store, hub, settings) }

        val body = client.get("/api/monitor").bodyAsText()
        // ignoreUnknownKeys=true：服务端新增字段时旧测试不挂
        val obj = json.parseToJsonElement(body).jsonObject
        assertTrue(obj.containsKey("serverTimeMs"), "serverTimeMs 字段缺失")
        val m: MonitorState = json.decodeFromString(body)
        assertEquals(fixedNow, m.serverTimeMs)
    }

    @Test
    fun `固定时钟下连续两次请求 serverTimeMs 单调不减`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val (store, hub, settings) = setup(tempDir, fixedNow)
        application { module(store, hub, settings) }

        val t1 = json.decodeFromString<MonitorState>(client.get("/api/monitor").bodyAsText()).serverTimeMs
        val t2 = json.decodeFromString<MonitorState>(client.get("/api/monitor").bodyAsText()).serverTimeMs
        assertTrue(t2 >= t1, "serverTimeMs 应单调不减")
        assertEquals(fixedNow, t2)
    }

    @Test
    fun `rehearsal 字段为布尔值可解码`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val (store, hub, settings) = setup(tempDir, fixedNow)
        application { module(store, hub, settings) }

        val body = client.get("/api/monitor").bodyAsText()
        val obj = json.parseToJsonElement(body).jsonObject
        val rehearsal = obj["rehearsal"]!!.jsonPrimitive.boolean
        assertEquals(false, rehearsal, "默认 rehearsal 应为 false")
    }
}
