package dev.stagecue.server.config

import io.ktor.server.cio.CIO
import io.ktor.server.engine.ApplicationEngineFactory
import io.ktor.server.netty.Netty

/**
 * 按配置名选择 Ktor HTTP 引擎工厂。
 * cio 为默认；netty 供生产/CI 环境使用（本 VM 上 Netty 曾误用 KQueue 启动失败，见 TECH_DEBT #7）。
 * 未知名称抛 ConfigException，启动即失败，不静默回退。
 */
fun httpEngineFactory(name: String): ApplicationEngineFactory<*, *> =
    when (name.lowercase()) {
        "cio" -> CIO
        "netty" -> Netty
        else -> throw ConfigException("STAGECUE_HTTP_ENGINE 必须是 cio/netty 之一，当前值：'$name'")
    }
