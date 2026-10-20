package dev.stagecue.server

import dev.stagecue.server.db.Database
import dev.stagecue.server.db.SettingsStore
import dev.stagecue.server.db.SqliteShowStore
import dev.stagecue.shared.model.Cue
import dev.stagecue.shared.model.CueType
import dev.stagecue.shared.model.MonitorState
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import kotlinx.serialization.json.Json
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * SyncHub 时钟注入语义的集成测试（走 /api/monitor 真实端点）。
 *
 * 约定（以 MonitorApiTest 已验证用法为准）：
 * - ds = Database.init(tempDir)；store = SqliteShowStore(ds)；settings = SettingsStore(ds)
 * - hub = SyncHub(clock = { fixedNow })；testApplication { application { module(store, hub, settings) } }
 * - JSON 用 Json { ignoreUnknownKeys = true } 解码为 MonitorState，不做字符串 contains 断言
 */
class SyncHubClockDeepTest {

    private val json = Json { ignoreUnknownKeys = true }

    private fun snapshot(body: String): MonitorState = json.decodeFromString(body)

    @Test
    fun `固定时钟下 serverTimeMs 精确等于注入值且两次请求一致`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(clock = { fixedNow })
        application { module(store, hub, settings) }

        val m1 = snapshot(client.get("/api/monitor").bodyAsText())
        val m2 = snapshot(client.get("/api/monitor").bodyAsText())

        assertEquals(fixedNow, m1.serverTimeMs, "serverTimeMs 应精确等于注入的固定时钟值")
        assertEquals(fixedNow, m2.serverTimeMs, "第二次请求也应精确等于注入的固定时钟值")
    }

    @Test
    fun `未注入时钟时 serverTimeMs 落在请求前后区间内`(@TempDir tempDir: File) = testApplication {
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub()
        application { module(store, hub, settings) }

        val before = System.currentTimeMillis()
        val m = snapshot(client.get("/api/monitor").bodyAsText())
        val after = System.currentTimeMillis()

        // 时间敏感：仅作冒烟，允许少量抖动余量
        assertTrue(
            m.serverTimeMs >= before - 100 && m.serverTimeMs <= after + 100,
            "serverTimeMs=${m.serverTimeMs} 应落在请求区间 [$before, $after] 附近（仅冒烟）"
        )
    }

    @Test
    fun `非排练模式下 rehearsal 为 false 且 remainingMs 为 null`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(clock = { fixedNow })
        application { module(store, hub, settings) }

        val m = snapshot(client.get("/api/monitor").bodyAsText())

        assertEquals(false, m.rehearsal, "初始状态下 rehearsal 应为 false")
        assertNull(m.remainingMs, "非排练/无当前 cue 时 remainingMs 应为 null")
        assertEquals(fixedNow, m.serverTimeMs)
    }

    @Test
    fun `空 show 时 next 为 null`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(clock = { fixedNow })
        application { module(store, hub, settings) }

        val m = snapshot(client.get("/api/monitor").bodyAsText())

        assertNull(m.next, "空 show 时 next 应为 null")
        assertNull(m.current, "空 show 时 current 应为 null")
    }

    @Test
    fun `show 有 cue-001 时 next id 为 cue-001`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(clock = { fixedNow })
        store.addCue(Cue(id = "cue-001", name = "开场", type = CueType.AUDIO, durationMs = 60000, order = 1))
        application { module(store, hub, settings) }

        val m = snapshot(client.get("/api/monitor").bodyAsText())

        assertEquals("cue-001", m.next?.id, "next.id 应精确为 cue-001")
        assertEquals(fixedNow, m.serverTimeMs)
    }

    @Test
    fun `快照各字段类型正确可解码`(@TempDir tempDir: File) = testApplication {
        val fixedNow = 1_700_000_000_000L
        val ds = Database.init(tempDir)
        val store = SqliteShowStore(ds)
        val settings = SettingsStore(ds)
        val hub = SyncHub(clock = { fixedNow })
        application { module(store, hub, settings) }

        val response = client.get("/api/monitor")
        assertEquals(HttpStatusCode.OK, response.status)
        val m = snapshot(response.bodyAsText())

        // 全字段可达：任一字段解码失败即抛错，走到这里即通过
        assertTrue(m.serverTimeMs > 0, "serverTimeMs 应为正数")
    }
}
