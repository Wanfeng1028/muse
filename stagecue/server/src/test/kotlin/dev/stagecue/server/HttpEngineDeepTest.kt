package dev.stagecue.server

import dev.stagecue.server.config.ConfigException
import dev.stagecue.server.config.ServerConfig
import dev.stagecue.server.config.httpEngineFactory
import io.ktor.server.cio.CIO
import io.ktor.server.netty.Netty
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertSame
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class HttpEngineDeepTest {

    @Test
    fun `STAGECUE_HTTP_ENGINE 未设置时默认为 cio`() {
        val config = ServerConfig.fromEnv(emptyMap())
        assertEquals("cio", config.httpEngine)
    }

    @Test
    fun `netty 原样通过`() {
        val config = ServerConfig.fromEnv(mapOf("STAGECUE_HTTP_ENGINE" to "netty"))
        assertEquals("netty", config.httpEngine)
    }

    @Test
    fun `NETTY 大写归一化为 netty`() {
        val config = ServerConfig.fromEnv(mapOf("STAGECUE_HTTP_ENGINE" to "NETTY"))
        assertEquals("netty", config.httpEngine)
    }

    @Test
    fun `CIO 大写归一化为 cio`() {
        val config = ServerConfig.fromEnv(mapOf("STAGECUE_HTTP_ENGINE" to "CIO"))
        assertEquals("cio", config.httpEngine)
    }

    @Test
    fun `非法值 jetty 抛 ConfigException`() {
        val ex = assertThrows(ConfigException::class.java) {
            ServerConfig.fromEnv(mapOf("STAGECUE_HTTP_ENGINE" to "jetty"))
        }
        assertTrue(ex.message!!.contains("STAGECUE_HTTP_ENGINE"))
    }

    @Test
    fun `空字符串抛 ConfigException`() {
        val ex = assertThrows(ConfigException::class.java) {
            ServerConfig.fromEnv(mapOf("STAGECUE_HTTP_ENGINE" to ""))
        }
        assertTrue(ex.message!!.contains("STAGECUE_HTTP_ENGINE"))
    }

    @Test
    fun `data class 默认值为 cio`() {
        assertEquals("cio", ServerConfig().httpEngine)
    }

    @Test
    fun `cio 返回 CIO 单例`() {
        assertSame(CIO, httpEngineFactory("cio"))
    }

    @Test
    fun `netty 返回 Netty 单例`() {
        assertSame(Netty, httpEngineFactory("netty"))
    }

    @Test
    fun `NETTY 大写返回 Netty`() {
        assertSame(Netty, httpEngineFactory("NETTY"))
    }

    @Test
    fun `非法名抛 ConfigException`() {
        val ex = assertThrows(ConfigException::class.java) {
            httpEngineFactory("jetty")
        }
        assertTrue(ex.message!!.contains("STAGECUE_HTTP_ENGINE"))
    }

    @Test
    fun `fromEnv 与 factory 联动`() {
        val c = ServerConfig.fromEnv(mapOf("STAGECUE_HTTP_ENGINE" to "Netty"))
        assertSame(Netty, httpEngineFactory(c.httpEngine))
    }
}
