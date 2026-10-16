package dev.stagecue.server.config

import java.io.File
import kotlin.system.exitProcess

/** 配置校验失败异常，携带中文错误信息。 */
class ConfigException(message: String) : IllegalArgumentException(message)

/** 启动配置，所有字段均可从环境变量覆盖。 */
data class ServerConfig(
    val port: Int = 8080,
    val host: String = "0.0.0.0",
    val dataDir: File = File("./data"),
    val logLevel: String = "INFO",
    val wsPingIntervalMs: Long = 15000,
    val corsAllowedOrigins: String = "*",
    val rateLimitRps: Int = 60,
    val rateLimitBurst: Int = 120,
) {
    companion object {
        /** 从环境变量读取并校验配置，失败抛 [ConfigException]。 */
        fun fromEnv(env: Map<String, String?> = System.getenv()): ServerConfig {
            val port = env["STAGECUE_PORT"]?.let { raw ->
                val v = raw.toIntOrNull()
                    ?: throw ConfigException("STAGECUE_PORT 必须是 1~65535 的整数，当前值：'$raw'")
                if (v !in 1..65535) {
                    throw ConfigException("STAGECUE_PORT 必须是 1~65535 的整数，当前值：'$raw'")
                }
                v
            } ?: 8080

            val host = env["STAGECUE_HOST"]?.let { raw ->
                if (raw.isBlank()) {
                    throw ConfigException("STAGECUE_HOST 不能为空，当前值：'$raw'")
                }
                raw
            } ?: "0.0.0.0"

            val dataDir = env["STAGECUE_DATA_DIR"]?.let { raw ->
                if (raw.isBlank()) {
                    throw ConfigException("STAGECUE_DATA_DIR 不能为空，当前值：'$raw'")
                }
                val f = File(raw)
                if (!f.exists()) {
                    f.mkdirs()
                }
                if (!f.isDirectory) {
                    throw ConfigException("STAGECUE_DATA_DIR 不是目录：'${f.absolutePath}'（存在但不是目录）")
                }
                if (!f.canWrite()) {
                    throw ConfigException("STAGECUE_DATA_DIR 不可写：'${f.absolutePath}'")
                }
                f
            } ?: File("./data").also {
                if (!it.exists()) it.mkdirs()
                if (!it.isDirectory) {
                    throw ConfigException("STAGECUE_DATA_DIR 不是目录：'${it.absolutePath}'")
                }
                if (!it.canWrite()) {
                    throw ConfigException("STAGECUE_DATA_DIR 不可写：'${it.absolutePath}'")
                }
            }

            val logLevel = env["STAGECUE_LOG_LEVEL"]?.let { raw ->
                val upper = raw.uppercase()
                if (upper !in setOf("DEBUG", "INFO", "WARN", "ERROR")) {
                    throw ConfigException(
                        "STAGECUE_LOG_LEVEL 必须是 DEBUG/INFO/WARN/ERROR 之一，当前值：'$raw'"
                    )
                }
                upper
            } ?: "INFO"

            val wsPingIntervalMs = env["STAGECUE_WS_PING_INTERVAL_MS"]?.let { raw ->
                val v = raw.toLongOrNull()
                    ?: throw ConfigException("STAGECUE_WS_PING_INTERVAL_MS 必须是 >= 1000 的整数，当前值：'$raw'")
                if (v < 1000L) {
                    throw ConfigException("STAGECUE_WS_PING_INTERVAL_MS 必须是 >= 1000 的整数，当前值：'$raw'")
                }
                v
            } ?: 15000L

            val corsAllowedOrigins = env["STAGECUE_CORS_ALLOWED_ORIGINS"]?.let { raw ->
                if (raw.isBlank()) {
                    throw ConfigException("STAGECUE_CORS_ALLOWED_ORIGINS 不能为空，当前值：'$raw'")
                }
                raw
            } ?: "*"

            val rateLimitRps = env["STAGECUE_RATE_LIMIT_RPS"]?.let { raw ->
                val v = raw.toIntOrNull()
                    ?: throw ConfigException("STAGECUE_RATE_LIMIT_RPS 必须是 >= 1 的整数，当前值：'$raw'")
                if (v < 1) {
                    throw ConfigException("STAGECUE_RATE_LIMIT_RPS 必须是 >= 1 的整数，当前值：'$raw'")
                }
                v
            } ?: 60

            val rateLimitBurst = env["STAGECUE_RATE_LIMIT_BURST"]?.let { raw ->
                val v = raw.toIntOrNull()
                    ?: throw ConfigException("STAGECUE_RATE_LIMIT_BURST 必须是 >= 1 的整数，当前值：'$raw'")
                if (v < 1) {
                    throw ConfigException("STAGECUE_RATE_LIMIT_BURST 必须是 >= 1 的整数，当前值：'$raw'")
                }
                v
            } ?: 120

            return ServerConfig(
                port = port,
                host = host,
                dataDir = dataDir,
                logLevel = logLevel,
                wsPingIntervalMs = wsPingIntervalMs,
                corsAllowedOrigins = corsAllowedOrigins,
                rateLimitRps = rateLimitRps,
                rateLimitBurst = rateLimitBurst,
            )
        }
    }

    /** 校验配置，失败时打错误日志并退出 JVM（exit code 1）。 */
    fun validateOrExit(): ServerConfig = try {
        fromEnv()
    } catch (e: ConfigException) {
        System.err.println("配置错误：${e.message}")
        exitProcess(1)
    }
}
