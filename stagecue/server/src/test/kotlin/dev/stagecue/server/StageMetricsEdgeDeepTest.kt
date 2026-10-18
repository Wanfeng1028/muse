package dev.stagecue.server

import dev.stagecue.server.metrics.StageMetrics
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

/**
 * 深度边界测试：覆盖 StageMetrics 中此前未被已有测试触及的计数器/gauge。
 * 每个用例都 new 一个独立的 StageMetrics()，保证注册表互不干扰。
 *
 * 关于子串断言的说明：
 * Prometheus 文本暴露格式每行形如 `stagecue_x 1.0`，或带标签 `stagecue_x{a="b",} 1.0`。
 * 输出中还包含 `# HELP`/`# TYPE` 注释行，且标签的渲染顺序由底层客户端决定，
 * 因此整行精确匹配非常脆弱。这里统一用 contains 做子串匹配，
 * 且选择足够独特、能唯一锚定目标样本的子串。
 */
class StageMetricsEdgeDeepTest {

    @Test
    fun `ws connections and disconnections counted separately`() {
        // 推导：wsConnected() 与 wsDisconnected() 分别操作两个独立 Counter。
        // 调用 2 次连接、1 次断开后，两个样本各自反映自己的累计次数，
        // 断言两个独立子串以证明它们没有被合并或串扰。
        val metrics = StageMetrics()
        metrics.wsConnected()
        metrics.wsConnected()
        metrics.wsDisconnected()

        val text = metrics.scrape()

        // 子串 "stagecue_ws_connections_total 2.0"：Counter 名为 stagecue_ws_connections，
        // 累计 2 次后值恰为 2.0（Prometheus 数值以浮点渲染）。
        assertTrue(
            text.contains("stagecue_ws_connections_total 2.0"),
            "expected ws_connections counter to be 2.0, scrape was:\n$text"
        )
        // 子串 "stagecue_ws_disconnections_total 1.0"：独立 Counter，仅断开一次，值 1.0。
        assertTrue(
            text.contains("stagecue_ws_disconnections_total 1.0"),
            "expected ws_disconnections counter to be 1.0, scrape was:\n$text"
        )
    }

    @Test
    fun `cueTriggered splits rehearsal labels`() {
        // 推导：cueTriggered(rehearsal) 根据布尔值写入两个不同带标签的 Counter。
        // true 调 1 次、false 调 2 次后，两个标签序列的样本值应分别为 1.0 与 2.0。
        // Prometheus 渲染单标签为 `...{rehearsal="true"} 1.0`（无尾逗号），用该子串锚定。
        // 这是该样本唯一可区分的片段（既含标签值又含数值），避免整行匹配的脆弱性。
        val metrics = StageMetrics()
        metrics.cueTriggered(true)
        metrics.cueTriggered(false)
        metrics.cueTriggered(false)

        val text = metrics.scrape()

        assertTrue(
            text.contains("rehearsal=\"true\"} 1.0"),
            "expected rehearsal=true sample with value 1.0, scrape was:\n$text"
        )
        assertTrue(
            text.contains("rehearsal=\"false\"} 2.0"),
            "expected rehearsal=false sample with value 2.0, scrape was:\n$text"
        )
    }

    @Test
    fun `cueArmed counted`() {
        // 推导：cueArmed() 每次自增 stagecue_cues_armed。调用 3 次后值应为 3.0。
        // 用 "stagecue_cues_armed_total 3.0" 锚定，避免与其他 cue 相关样本混淆。
        val metrics = StageMetrics()
        metrics.cueArmed()
        metrics.cueArmed()
        metrics.cueArmed()

        val text = metrics.scrape()

        assertTrue(
            text.contains("stagecue_cues_armed_total 3.0"),
            "expected cues_armed counter to be 3.0, scrape was:\n$text"
        )
    }

    @Test
    fun `broadcastDropped accumulates exact amount`() {
        // 推导：broadcastDropped(n) 用 increment(n.toDouble()) 一次性增加 n。
        // 单次调用 broadcastDropped(5) 后累计值应精确为 5.0，
        // 用 "stagecue_ws_broadcast_dropped_total 5.0" 锚定，验证增量语义而非计数次数。
        val metrics = StageMetrics()
        metrics.broadcastDropped(5)

        val text = metrics.scrape()

        assertTrue(
            text.contains("stagecue_ws_broadcast_dropped_total 5.0"),
            "expected broadcast_dropped_total to be 5.0, scrape was:\n$text"
        )
    }

    @Test
    fun `dbMigrationsApplied gauge reflects last set`() {
        // 推导：dbMigrationsApplied(n) 调用 gauge.set(n)，是"设为"而非"累加"。
        // 先 set 3 再 set 7，gauge 应只反映最后一次赋值 7.0，而不是 3+7=10。
        // 先断言 3.0 子串存在（第一次 set 生效），再断言 7.0 子串存在（第二次覆盖生效）。
        // 由于 scrape 只反映当前状态，若实现错误累加则会看到 10.0 而两个子串都失败。
        val metrics = StageMetrics()
        metrics.dbMigrationsApplied(3)

        val afterFirst = metrics.scrape()
        assertTrue(
            afterFirst.contains("stagecue_db_migrations_applied 3.0"),
            "expected migrations gauge to be 3.0 after first set, scrape was:\n$afterFirst"
        )

        metrics.dbMigrationsApplied(7)
        val afterSecond = metrics.scrape()
        // 子串 "stagecue_db_migrations_applied 7.0"：第二次 set 覆盖后的最终值。
        assertTrue(
            afterSecond.contains("stagecue_db_migrations_applied 7.0"),
            "expected migrations gauge to be 7.0 after second set (set semantics, not accumulation), scrape was:\n$afterSecond"
        )
    }

    @Test
    fun `fresh metrics start at zero`() {
        // 推导：Prometheus Counter 在注册时即被初始化为 0，
        // 因此一个全新的 StageMetrics 未调用任何方法时，
        // stagecue_ws_connections 样本应已存在且值为 0.0。
        // 断言 "stagecue_ws_connections_total 0.0" 证明计数器已注册且初值为零。
        val metrics = StageMetrics()

        val text = metrics.scrape()

        assertTrue(
            text.contains("stagecue_ws_connections_total 0.0"),
            "expected fresh ws_connections counter to be 0.0, scrape was:\n$text"
        )
    }

    @Test
    fun `showRequested increments one by one`() {
        // 推导：showRequested() 每次自增 stagecue_http_show_requests。
        // 单次调用后值应为 1.0，用 "stagecue_http_show_requests_total 1.0" 锚定，
        // 验证单次自增语义（与已有的"两次"测试场景互补但不重复）。
        val metrics = StageMetrics()
        metrics.showRequested()

        val text = metrics.scrape()

        assertTrue(
            text.contains("stagecue_http_show_requests_total 1.0"),
            "expected http_show_requests counter to be 1.0 after single call, scrape was:\n$text"
        )
    }

    @Test
    fun `httpRateLimited counted`() {
        // 推导：httpRateLimited() 每次自增 stagecue_http_rate_limited_total。
        // 调用 2 次后累计值应为 2.0。
        // 注意样本名带 _total 后缀，用完整名加数值锚定以避免与其它 http 样本混淆。
        val metrics = StageMetrics()
        metrics.httpRateLimited()
        metrics.httpRateLimited()

        val text = metrics.scrape()

        assertTrue(
            text.contains("stagecue_http_rate_limited_total 2.0"),
            "expected http_rate_limited_total to be 2.0, scrape was:\n$text"
        )
    }
}
