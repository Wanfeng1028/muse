package com.dramafactory.metrics;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

/**
 * 针对 DramaMetrics 分支覆盖的补充测试。
 * 不启动 Spring 上下文；构造器传入 null repository 是安全的（refresh() 内部 try/catch 包住 DB 异常）。
 */
class DramaMetricsBranchTest {

    /**
     * 覆盖第 97 行三元表达式 model == null 臂：
     * (model == null || model.isBlank()) ? "unknown" : model
     * 传 null 时应归一化为 "unknown"。
     */
    @Test
    void recordScriptLlm_whenModelIsNull_normalizesToUnknown() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        DramaMetrics metrics = new DramaMetrics(registry, null, null);

        assertDoesNotThrow(() -> metrics.recordScriptLlm(null, 100L, true));

        assertEquals(1.0,
                registry.counter("dramafactory_script_llm_calls_total",
                        "model", "unknown", "result", "ok").count(),
                0.0);
    }

    /**
     * 覆盖第 97 行三元表达式 model.isBlank() 臂：
     * 传空白字符串时应归一化为 "unknown"，且 result 为 "error"。
     */
    @Test
    void recordScriptLlm_whenModelIsBlank_normalizesToUnknownAndResultError() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        DramaMetrics metrics = new DramaMetrics(registry, null, null);

        assertDoesNotThrow(() -> metrics.recordScriptLlm(" ", 100L, false));

        assertEquals(1.0,
                registry.counter("dramafactory_script_llm_calls_total",
                        "model", "unknown", "result", "error").count(),
                0.0);
    }

    /**
     * 覆盖第 115 行三元表达式 ok ? "ok" : "error" 的 ok == false 臂：
     * recordFinalCutBuild(50L, false) 应使 result="error" 的 counter 计数为 1。
     */
    @Test
    void recordFinalCutBuild_whenOkIsFalse_incrementsErrorCounter() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        DramaMetrics metrics = new DramaMetrics(registry, null, null);

        metrics.recordFinalCutBuild(50L, false);

        assertEquals(1.0,
                registry.counter("dramafactory_finalcut_builds_total",
                        "result", "error").count(),
                0.0);
    }

    /**
     * 回归保护：负延迟应被 Math.max(0L, latencyMs) 截断为 0，且不抛异常。
     * （该分支已被覆盖，此处仅作行为保护。）
     */
    @Test
    void recordFinalCutBuild_whenLatencyNegative_clampsToZeroAndDoesNotThrow() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        DramaMetrics metrics = new DramaMetrics(registry, null, null);

        assertDoesNotThrow(() -> metrics.recordFinalCutBuild(-5L, true));

        assertEquals(1.0,
                registry.counter("dramafactory_finalcut_builds_total",
                        "result", "ok").count(),
                0.0);
    }
}