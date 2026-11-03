package dev.stagecue.server.metrics

import io.micrometer.core.instrument.Counter
import io.micrometer.prometheusmetrics.PrometheusConfig
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry
import java.util.concurrent.atomic.AtomicInteger

/**
 * stagecue 运行时指标集合，暴露为 Prometheus 文本格式。
 */
class StageMetrics {

    private val registry = PrometheusMeterRegistry(PrometheusConfig.DEFAULT)

    private val wsConnections: Counter = Counter
        .builder("stagecue_ws_connections")
        .description("WebSocket 连接建立次数")
        .register(registry)

    private val wsDisconnections: Counter = Counter
        .builder("stagecue_ws_disconnections")
        .description("WebSocket 连接断开次数")
        .register(registry)

    private val cuesTriggeredTrue: Counter = Counter
        .builder("stagecue_cues_triggered")
        .description("cue 触发次数（按是否排练打标签）")
        .tag("rehearsal", "true")
        .register(registry)

    private val cuesTriggeredFalse: Counter = Counter
        .builder("stagecue_cues_triggered")
        .description("cue 触发次数（按是否排练打标签）")
        .tag("rehearsal", "false")
        .register(registry)

    private val cuesArmed: Counter = Counter
        .builder("stagecue_cues_armed")
        .description("cue 待命（arm）次数")
        .register(registry)

    private val httpShowRequests: Counter = Counter
        .builder("stagecue_http_show_requests")
        .description("GET /api/show 请求次数")
        .register(registry)

    private val httpRateLimited: Counter = Counter
        .builder("stagecue_http_rate_limited_total")
        .description("HTTP 请求被限流拒绝次数（429）")
        .register(registry)

    private val wsBroadcastDropped: Counter = Counter
        .builder("stagecue_ws_broadcast_dropped_total")
        .description("WS 广播因慢消费者丢弃的消息数（DROP_OLDEST 策略）")
        .register(registry)

    private val migrationsApplied = AtomicInteger(0)

    init {
        registry.gauge("stagecue_db_migrations_applied", migrationsApplied)
    }

    fun wsConnected() {
        wsConnections.increment()
    }

    fun wsDisconnected() {
        wsDisconnections.increment()
    }

    fun cueTriggered(rehearsal: Boolean) {
        if (rehearsal) cuesTriggeredTrue.increment() else cuesTriggeredFalse.increment()
    }

    fun cueArmed() {
        cuesArmed.increment()
    }

    fun showRequested() {
        httpShowRequests.increment()
    }

    fun dbMigrationsApplied(n: Int) {
        migrationsApplied.set(n)
    }

    fun httpRateLimited() {
        httpRateLimited.increment()
    }

    fun broadcastDropped(n: Long) {
        wsBroadcastDropped.increment(n.toDouble())
    }

    fun scrape(): String = registry.scrape()
}
