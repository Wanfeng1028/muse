package dev.stagecue.server

import dev.stagecue.server.config.ConfigException
import dev.stagecue.server.config.ServerConfig

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/**
 * 针对 [ServerConfig.fromEnv] 中 STAGECUE_HTTP_ENGINE 解析语义的单元测试。
 *
 * 测试语义总览（严格对照源码 fromEnv 实现）：
 * - 未设置 STAGECUE_HTTP_ENGINE：httpEngine 默认 "cio"。
 * - 设置 "netty"：httpEngine == "netty"。
 * - 设置 "CIO"：源码执行 raw.lowercase() 后再比较，因此 "CIO" 合法，httpEngine == "cio"（被归一化为小写）。
 * - 设置 "jetty"：lowercase 后既非 "cio" 也非 "netty"，抛 ConfigException（fail-fast，不静默回退）。
 * - 设置空串 ""：lowercase 后为空串，仍不等于 "cio"/"netty"，抛 ConfigException。
 * - httpEngine 解析位于 fromEnv 的最后一步，与其他字段（port/host 等）解析相互独立、正交。
 * - 解析顺序：port -> host -> dataDir -> logLevel -> wsPingIntervalMs -> corsAllowedOrigins
 *   -> rateLimitRps -> rateLimitBurst -> httpEngine。因此多个非法项同时存在时，先解析到的非法项先抛，
 *   即 port 的非法优先于 httpEngine 的非法。
 *
 * 所有环境变量均通过 Map 参数注入，不触碰真实 System.getenv()。
 * 所有测试都在 @TempDir 下提供 dataDir，避免依赖真实 ./data 目录。
 */
class ServerConfigHttpEngineDeepTest {

    /**
     * 构造一份"合法基础环境变量"，其中 dataDir 指向 @TempDir，避免污染工作目录。
     * 不包含 STAGECUE_HTTP_ENGINE，因此可在此基础上按需覆盖。
     */
    private fun baseEnv(dataDir: File): MutableMap<String, String?> = mutableMapOf(
        "STAGECUE_DATA_DIR" to dataDir.absolutePath,
    )

    /** 未设置 STAGECUE_HTTP_ENGINE 时，应落到源码默认值 "cio"。 */
    @Test
    fun `未设置环境变量时 httpEngine 默认 cio`(@TempDir dataDir: File) {
        val env = baseEnv(dataDir)

        val config = ServerConfig.fromEnv(env)

        assertEquals("cio", config.httpEngine, "未提供 STAGECUE_HTTP_ENGINE 时应默认 cio")
    }

    /** 显式设置 "netty" 时，应原样归一化为 "netty"。 */
    @Test
    fun `设置 netty 时 httpEngine 为 netty`(@TempDir dataDir: File) {
        val env = baseEnv(dataDir).apply {
            put("STAGECUE_HTTP_ENGINE", "netty")
        }

        val config = ServerConfig.fromEnv(env)

        assertEquals("netty", config.httpEngine)
    }

    /**
     * 设置 "CIO"（大写）时，源码先执行 raw.lowercase() 再比较，
     * 因此 "CIO" 是合法值，且 httpEngine 被归一化为小写 "cio"（而非原样保留）。
     */
    @Test
    fun `设置大写 CIO 时被归一化为小写 cio`(@TempDir dataDir: File) {
        val env = baseEnv(dataDir).apply {
            put("STAGECUE_HTTP_ENGINE", "CIO")
        }

        val config = ServerConfig.fromEnv(env)

        assertEquals("cio", config.httpEngine, "CIO 应被 lowercase 归一化为 cio")
    }

    /** 设置非法的 "jetty" 时必须 fail-fast 抛 ConfigException，绝不静默回退到 cio。 */
    @Test
    fun `设置 jetty 时抛 ConfigException 不静默回退`(@TempDir dataDir: File) {
        val env = baseEnv(dataDir).apply {
            put("STAGECUE_HTTP_ENGINE", "jetty")
        }

        val ex = assertThrows<ConfigException> {
            ServerConfig.fromEnv(env)
        }

        assertTrue(
            ex.message!!.contains("STAGECUE_HTTP_ENGINE"),
            "错误信息应指向 STAGECUE_HTTP_ENGINE，实际为：${ex.message}",
        )
    }

    /**
     * 设置空串 ""：lowercase 后仍为空串，不等于 "cio"/"netty"，
     * 因此按源码语义抛 ConfigException（空串不是"未设置"，不会被当成默认值）。
     */
    @Test
    fun `设置空串时抛 ConfigException`(@TempDir dataDir: File) {
        val env = baseEnv(dataDir).apply {
            put("STAGECUE_HTTP_ENGINE", "")
        }

        val ex = assertThrows<ConfigException> {
            ServerConfig.fromEnv(env)
        }

        assertTrue(
            ex.message!!.contains("STAGECUE_HTTP_ENGINE"),
            "错误信息应指向 STAGECUE_HTTP_ENGINE，实际为：${ex.message}",
        )
    }

    /** httpEngine 与 port/host 正交：改 engine 不影响 port/host 的解析结果。 */
    @Test
    fun `httpEngine 与 port 和 host 正交解析`(@TempDir dataDir: File) {
        val env = baseEnv(dataDir).apply {
            put("STAGECUE_HTTP_ENGINE", "netty")
            put("STAGECUE_PORT", "9001")
            put("STAGECUE_HOST", "127.0.0.1")
        }

        val config = ServerConfig.fromEnv(env)

        assertEquals("netty", config.httpEngine)
        assertEquals(9001, config.port)
        assertEquals("127.0.0.1", config.host)
    }

    /**
     * 多个非法项同时存在时的报错优先级：fromEnv 按固定顺序解析，
     * STAGECUE_PORT 先于 STAGECUE_HTTP_ENGINE 被解析，因此二者都非法时先抛 port 的错误。
     * 这里断言错误信息指向 STAGECUE_PORT，而非 STAGECUE_HTTP_ENGINE。
     */
    @Test
    fun `port 非法优先于 httpEngine 非法被抛出`(@TempDir dataDir: File) {
        val env = baseEnv(dataDir).apply {
            put("STAGECUE_PORT", "not-a-number")
            put("STAGECUE_HTTP_ENGINE", "jetty")
        }

        val ex = assertThrows<ConfigException> {
            ServerConfig.fromEnv(env)
        }

        assertTrue(
            ex.message!!.contains("STAGECUE_PORT"),
            "port 先于 httpEngine 解析，错误应指向 STAGECUE_PORT，实际为：${ex.message}",
        )
    }
}