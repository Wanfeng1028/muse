package com.dramafactory.metrics;

import com.dramafactory.repository.RunRepository;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

@SpringBootTest
class DramaMetricsDeepTestR4 {

    @Autowired
    private DramaMetrics dramaMetrics;

    @Autowired
    private MeterRegistry registry;

    @MockBean
    private RunRepository runRepository;

    private double countScript(String model, String result) {
        Counter c = registry.find("dramafactory_script_llm_calls_total")
                .tag("model", model)
                .tag("result", result)
                .counter();
        return c == null ? 0.0 : c.count();
    }

    private double countFinalCut(String result) {
        Counter c = registry.find("dramafactory_finalcut_builds_total")
                .tag("result", result)
                .counter();
        return c == null ? 0.0 : c.count();
    }

    private double countFfmpeg(String operation, String kind, String result) {
        Counter c = registry.find("dramafactory_ffmpeg_retries_total")
                .tag("operation", operation)
                .tag("kind", kind)
                .tag("result", result)
                .counter();
        return c == null ? 0.0 : c.count();
    }

    private double countPollSkipped() {
        Counter c = registry.find("dramafactory_video_poll_skipped_total").counter();
        return c == null ? 0.0 : c.count();
    }

    @Test
    void recordScriptLlm_ok_incrementsOkCounter() {
        String model = "m-r4a-" + System.nanoTime();
        double before = countScript(model, "ok");
        dramaMetrics.recordScriptLlm(model, 100L, true);
        double after = countScript(model, "ok");
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, after, 1e-9);
    }

    @Test
    void recordScriptLlm_error_incrementsErrorCounter() {
        String model = "m-r4a-" + System.nanoTime();
        double before = countScript(model, "error");
        dramaMetrics.recordScriptLlm(model, 100L, false);
        double after = countScript(model, "error");
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, after, 1e-9);
    }

    @Test
    void recordScriptLlm_negativeLatency_doesNotThrow() {
        String model = "m-r4a-" + System.nanoTime();
        double before = countScript(model, "ok");
        assertDoesNotThrow(() -> dramaMetrics.recordScriptLlm(model, -5L, true));
        double after = countScript(model, "ok");
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, after, 1e-9);
    }

    @Test
    void recordScriptLlm_zeroLatency_ok() {
        String model = "m-r4a-" + System.nanoTime();
        assertDoesNotThrow(() -> dramaMetrics.recordScriptLlm(model, 0L, true));
    }

    @Test
    void recordFinalCutBuild_ok_increments() {
        double before = countFinalCut("ok");
        dramaMetrics.recordFinalCutBuild(50L, true);
        double after = countFinalCut("ok");
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, after, 1e-9);
    }

    @Test
    void recordFfmpegRetry_transient_ok() {
        double before = countFfmpeg("op-r4a", "transient", "ok");
        dramaMetrics.recordFfmpegRetry("op-r4a", true, true);
        double after = countFfmpeg("op-r4a", "transient", "ok");
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, after, 1e-9);
    }

    @Test
    void recordFfmpegRetry_permanent_error() {
        double before = countFfmpeg("op-r4a-perm", "permanent", "error");
        dramaMetrics.recordFfmpegRetry("op-r4a-perm", false, false);
        double after = countFfmpeg("op-r4a-perm", "permanent", "error");
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, after, 1e-9);
    }

    @Test
    void recordFfmpegRetry_nullOperation_normalizesUnknown() {
        double before = countFfmpeg("unknown", "transient", "ok");
        dramaMetrics.recordFfmpegRetry(null, true, true);
        double after = countFfmpeg("unknown", "transient", "ok");
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, after, 1e-9);
    }

    @Test
    void recordFfmpegRetry_blankOperation_normalizesUnknown() {
        double before = countFfmpeg("unknown", "transient", "ok");
        dramaMetrics.recordFfmpegRetry("  ", true, true);
        double after = countFfmpeg("unknown", "transient", "ok");
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, after, 1e-9);
    }

    @Test
    void recordPollSkipped_increments() {
        double before = countPollSkipped();
        dramaMetrics.recordPollSkipped();
        double mid = countPollSkipped();
        org.junit.jupiter.api.Assertions.assertEquals(before + 1.0, mid, 1e-9);
        dramaMetrics.recordPollSkipped();
        double after = countPollSkipped();
        org.junit.jupiter.api.Assertions.assertEquals(mid + 1.0, after, 1e-9);
    }

    @Test
    void refresh_doesNotThrow() {
        assertDoesNotThrow(() -> dramaMetrics.refresh());
    }

    @Test
    void refresh_withBrokenRepository_doesNotThrow() {
        Mockito.when(runRepository.countByStatus(Mockito.any()))
                .thenThrow(new RuntimeException("boom-r4a"));
        assertDoesNotThrow(() -> dramaMetrics.refresh());
    }
}