package dev.stagecue.server

import dev.stagecue.server.config.ConfigException
import dev.stagecue.server.config.httpEngineFactory

import io.ktor.server.cio.CIO
import io.ktor.server.netty.Netty
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertSame
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import kotlin.reflect.KParameter
import kotlin.reflect.full.valueParameters
import kotlin.reflect.jvm.javaMethod

/**
 * httpEngineFactory 的语义测试：
 * - 已知名称大小写不敏感地映射到唯一的引擎工厂实例；
 * - 未知名称（含空串、带空格、非 cio/netty）一律抛 ConfigException，绝不静默回退；
 * - ConfigException 是 IllegalArgumentException 子类，且 message 保留非法值原文；
 * - 函数无状态，重复调用返回同一工厂实例；
 * - 参数在 Kotlin 类型系统层面为非空，反射确认无可空标记。
 */
class HttpEngineFactoryDeepTest {

    @Test
    fun `cio 返回 CIO 工厂同一实例`() {
        // 在测：小写 cio 必须精确映射到 io.ktor.server.cio.CIO 这一单例工厂。
        assertSame(CIO, httpEngineFactory("cio"))
    }

    @Test
    fun `netty 返回 Netty 工厂同一实例`() {
        // 在测：小写 netty 必须精确映射到 io.ktor.server.netty.Netty 这一单例工厂。
        assertSame(Netty, httpEngineFactory("netty"))
    }

    @Test
    fun `CIO 大写可解析到 CIO 工厂`() {
        // 在测：大小写不敏感——全大写 CIO 与 cio 等价。
        assertSame(CIO, httpEngineFactory("CIO"))
    }

    @Test
    fun `Netty 首字母大写可解析到 Netty 工厂`() {
        // 在测：大小写不敏感——首字母大写 Netty 与 netty 等价。
        assertSame(Netty, httpEngineFactory("Netty"))
    }

    @Test
    fun `Cio 混合大小写可解析到 CIO 工厂`() {
        // 在测：大小写不敏感——混合大小写 Cio 与 cio 等价。
        assertSame(CIO, httpEngineFactory("Cio"))
    }

    @Test
    fun `空串抛 ConfigException`() {
        // 在测：空串不是合法引擎名，必须启动即失败而非回退默认。
        assertThrows(ConfigException::class.java) {
            httpEngineFactory("")
        }
    }

    @Test
    fun `jetty 抛 ConfigException`() {
        // 在测：未支持的 jetty 引擎名必须被拒绝。
        assertThrows(ConfigException::class.java) {
            httpEngineFactory("jetty")
        }
    }

    @Test
    fun `tomcat 抛 ConfigException`() {
        // 在测：未支持的 tomcat 引擎名必须被拒绝。
        assertThrows(ConfigException::class.java) {
            httpEngineFactory("tomcat")
        }
    }

    @Test
    fun `前导空格 CIO 抛 ConfigException`() {
        // 在测：实现只做 lowercase() 不做 trim()，带前导空格的 " CIO" 是非法值。
        assertThrows(ConfigException::class.java) {
            httpEngineFactory(" CIO")
        }
    }

    @Test
    fun `ConfigException 是 IllegalArgumentException 子类`() {
        // 在测：异常层次——ConfigException 必须继承 IllegalArgumentException，便于调用方统一捕获配置错误。
        val ex = assertThrows(ConfigException::class.java) {
            httpEngineFactory("bogus")
        }
        assertTrue(ex is IllegalArgumentException)
    }

    @Test
    fun `非法值原文出现在异常 message 中`() {
        // 在测：错误信息必须回显非法值原文，方便定位配置问题。
        val ex = assertThrows(ConfigException::class.java) {
            httpEngineFactory("jetty")
        }
        val message = ex.message
        assertTrue(message != null && message.contains("jetty"))
    }

    @Test
    fun `带空格的非法值原文出现在异常 message 中`() {
        // 在测：即使非法值含空格，message 也必须完整回显原文（含空格）。
        val ex = assertThrows(ConfigException::class.java) {
            httpEngineFactory(" CIO")
        }
        val message = ex.message
        assertTrue(message != null && message.contains(" CIO"))
    }

    @Test
    fun `连续调用两次返回同一工厂实例`() {
        // 在测：when 表达式无状态，两次调用必须返回同一单例工厂实例。
        assertSame(httpEngineFactory("cio"), httpEngineFactory("cio"))
        assertSame(httpEngineFactory("netty"), httpEngineFactory("netty"))
    }

    @Test
    fun `参数为非空类型无空值标记`() {
        // 在测：Kotlin 非空类型保证 null 无法传入——反射确认参数类型无 isMarkedNullable 标记。
        val method = ::httpEngineFactory.javaMethod
        assertTrue(method != null)
        val parameters: List<KParameter> = ::httpEngineFactory.parameters
        // 第一个参数即 name（KParameter 集合不含实例接收者）。
        val nameParameter = parameters.first()
        assertFalse(nameParameter.type.isMarkedNullable)
    }
}