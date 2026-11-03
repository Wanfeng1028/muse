package dev.stagecue.server

import dev.stagecue.server.config.ConfigException
import dev.stagecue.server.config.ServerConfig
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class ServerConfigEdgeDeepTest {

    @Test
    fun `blank host throws`() {
        val ex = assertThrows(ConfigException::class.java) {
            ServerConfig.fromEnv(mapOf("STAGECUE_HOST" to "   "))
        }
        assertTrue(ex.message!!.contains("STAGECUE_HOST"))
    }

    @Test
    fun `custom host parsed`() {
        val config = ServerConfig.fromEnv(mapOf("STAGECUE_HOST" to "127.0.0.1"))
        assertEquals("127.0.0.1", config.host)
    }

    @Test
    fun `blank cors throws`() {
        val ex = assertThrows(ConfigException::class.java) {
            ServerConfig.fromEnv(mapOf("STAGECUE_CORS_ALLOWED_ORIGINS" to ""))
        }
        assertTrue(ex.message!!.contains("STAGECUE_CORS_ALLOWED_ORIGINS"))
    }

    @Test
    fun `custom cors parsed`() {
        val config = ServerConfig.fromEnv(
            mapOf("STAGECUE_CORS_ALLOWED_ORIGINS" to "https://a.example"),
        )
        assertEquals("https://a.example", config.corsAllowedOrigins)
    }

    @Test
    fun `blank dataDir throws`() {
        val ex = assertThrows(ConfigException::class.java) {
            ServerConfig.fromEnv(mapOf("STAGECUE_DATA_DIR" to "  "))
        }
        assertTrue(ex.message!!.contains("STAGECUE_DATA_DIR"))
    }

    @Test
    fun `ping interval custom valid parsed`() {
        val config = ServerConfig.fromEnv(mapOf("STAGECUE_WS_PING_INTERVAL_MS" to "2000"))
        assertEquals(2000L, config.wsPingIntervalMs)
    }

    @Test
    fun `ping interval non-numeric throws`() {
        val ex = assertThrows(ConfigException::class.java) {
            ServerConfig.fromEnv(mapOf("STAGECUE_WS_PING_INTERVAL_MS" to "abc"))
        }
        assertTrue(ex.message!!.contains("STAGECUE_WS_PING_INTERVAL_MS"))
    }

    @Test
    fun `defaults are complete`(@TempDir tempDir: File) {
        val config = ServerConfig.fromEnv(
            mapOf("STAGECUE_DATA_DIR" to tempDir.absolutePath),
        )
        assertEquals(8080, config.port)
        assertEquals("0.0.0.0", config.host)
        assertEquals("INFO", config.logLevel)
        assertEquals(15000L, config.wsPingIntervalMs)
        assertEquals("*", config.corsAllowedOrigins)
        assertEquals(60, config.rateLimitRps)
        assertEquals(120, config.rateLimitBurst)
    }

    @Test
    fun `log level is uppercased`() {
        val config = ServerConfig.fromEnv(mapOf("STAGECUE_LOG_LEVEL" to "debug"))
        assertEquals("DEBUG", config.logLevel)
    }
}
