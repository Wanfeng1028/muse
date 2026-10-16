package dev.stagecue.server

import dev.stagecue.server.config.ConfigException
import dev.stagecue.server.config.ServerConfig
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class ServerConfigTest {

    @TempDir
    lateinit var tempDir: File

    @Test
    fun `empty env uses defaults`() {
        val cfg = ServerConfig.fromEnv(emptyMap())
        assertEquals(8080, cfg.port)
        assertEquals("0.0.0.0", cfg.host)
        assertEquals(File("./data"), cfg.dataDir)
        assertEquals("INFO", cfg.logLevel)
        assertEquals(15000L, cfg.wsPingIntervalMs)
        assertEquals("*", cfg.corsAllowedOrigins)
        assertEquals(60, cfg.rateLimitRps)
        assertEquals(120, cfg.rateLimitBurst)
    }

    @Test
    fun `custom rate limit env parsed`() {
        val cfg = ServerConfig.fromEnv(
            mapOf(
                "STAGECUE_DATA_DIR" to tempDir.absolutePath,
                "STAGECUE_RATE_LIMIT_RPS" to "10",
                "STAGECUE_RATE_LIMIT_BURST" to "20",
            )
        )
        assertEquals(10, cfg.rateLimitRps)
        assertEquals(20, cfg.rateLimitBurst)
    }

    @Test
    fun `rate limit rps zero throws`() {
        assertThrows<ConfigException> {
            ServerConfig.fromEnv(
                mapOf(
                    "STAGECUE_DATA_DIR" to tempDir.absolutePath,
                    "STAGECUE_RATE_LIMIT_RPS" to "0",
                )
            )
        }
    }

    @Test
    fun `rate limit burst non-numeric throws`() {
        assertThrows<ConfigException> {
            ServerConfig.fromEnv(
                mapOf(
                    "STAGECUE_DATA_DIR" to tempDir.absolutePath,
                    "STAGECUE_RATE_LIMIT_BURST" to "abc",
                )
            )
        }
    }

    @Test
    fun `full custom env parsed`() {
        val cfg = ServerConfig.fromEnv(
            mapOf(
                "STAGECUE_PORT" to "9000",
                "STAGECUE_HOST" to "127.0.0.1",
                "STAGECUE_DATA_DIR" to tempDir.absolutePath,
                "STAGECUE_LOG_LEVEL" to "debug",
                "STAGECUE_WS_PING_INTERVAL_MS" to "5000",
                "STAGECUE_CORS_ALLOWED_ORIGINS" to "https://a.example",
            )
        )
        assertEquals(9000, cfg.port)
        assertEquals("127.0.0.1", cfg.host)
        assertEquals(tempDir.absolutePath, cfg.dataDir.absolutePath)
        assertEquals("DEBUG", cfg.logLevel)
        assertEquals(5000L, cfg.wsPingIntervalMs)
        assertEquals("https://a.example", cfg.corsAllowedOrigins)
    }

    @Test
    fun `port non-numeric throws`() {
        assertThrows<ConfigException> {
            ServerConfig.fromEnv(mapOf("STAGECUE_PORT" to "abc"))
        }
    }

    @Test
    fun `port zero throws`() {
        assertThrows<ConfigException> {
            ServerConfig.fromEnv(mapOf("STAGECUE_PORT" to "0"))
        }
    }

    @Test
    fun `port too large throws`() {
        assertThrows<ConfigException> {
            ServerConfig.fromEnv(mapOf("STAGECUE_PORT" to "70000"))
        }
    }

    @Test
    fun `invalid log level throws`() {
        val ex = assertThrows<ConfigException> {
            ServerConfig.fromEnv(mapOf("STAGECUE_LOG_LEVEL" to "TRACE"))
        }
        assertTrue(ex.message!!.contains("STAGECUE_LOG_LEVEL"))
    }

    @Test
    fun `ping below minimum throws`() {
        assertThrows<ConfigException> {
            ServerConfig.fromEnv(mapOf("STAGECUE_WS_PING_INTERVAL_MS" to "500"))
        }
    }

    @Test
    fun `dataDir pointing to existing file throws`() {
        val f = File(tempDir, "notadir.txt")
        f.writeText("x")
        assertThrows<ConfigException> {
            ServerConfig.fromEnv(mapOf("STAGECUE_DATA_DIR" to f.absolutePath))
        }
    }
}
