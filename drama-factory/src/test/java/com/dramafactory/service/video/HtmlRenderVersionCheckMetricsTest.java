package com.dramafactory.service.video;

import com.dramafactory.metrics.DramaMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.assertj.core.data.Offset;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;

class HtmlRenderVersionCheckMetricsTest {

    static class FakeRunner implements HtmlRenderVideoProvider.CommandRunner {
        volatile int exitCode = 0;
        volatile boolean throwOnRun = false;

        @Override
        public ExecResult run(List<String> command, Path workDir, long timeoutSeconds) throws IOException {
            if (throwOnRun) {
                throw new IOException("cli not found");
            }
            return new ExecResult(exitCode, "");
        }
    }

    @Test
    void record_ok_and_error_and_negative_latency_clamped() {
        var registry = new SimpleMeterRegistry();
        var metrics = new DramaMetrics(registry, null, null);
        metrics.recordHyperFramesVersionCheck(120, true);
        metrics.recordHyperFramesVersionCheck(-5, false);

        assertThat(registry.counter("dramafactory_hyperframes_version_checks_total", "result", "ok").count()).isEqualTo(1.0);
        assertThat(registry.counter("dramafactory_hyperframes_version_checks_total", "result", "error").count()).isEqualTo(1.0);
        var timer = registry.timer("dramafactory_hyperframes_version_check_duration");
        assertThat(timer.count()).isEqualTo(2);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isCloseTo(120.0, Offset.offset(1.0));
    }

    @Test
    void resolveEngine_version_ok_records_ok() {
        var registry = new SimpleMeterRegistry();
        var metrics = new DramaMetrics(registry, null, null);
        var fake = new FakeRunner();
        fake.exitCode = 0;
        var provider = new HtmlRenderVideoProvider(fake, metrics);
        provider.setEngineConfig("hyperframes");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.HYPERFRAMES, provider.resolveEngine());
        assertThat(registry.counter("dramafactory_hyperframes_version_checks_total", "result", "ok").count()).isEqualTo(1.0);
        assertThat(registry.timer("dramafactory_hyperframes_version_check_duration").count()).isEqualTo(1);
    }

    @Test
    void resolveEngine_version_nonzero_records_error_and_degrades() {
        var registry = new SimpleMeterRegistry();
        var metrics = new DramaMetrics(registry, null, null);
        var fake = new FakeRunner();
        fake.exitCode = 3;
        var provider = new HtmlRenderVideoProvider(fake, metrics);
        provider.setEngineConfig("hyperframes");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.CHROMIUM, provider.resolveEngine());
        assertThat(registry.counter("dramafactory_hyperframes_version_checks_total", "result", "error").count()).isEqualTo(1.0);
    }

    @Test
    void resolveEngine_version_throws_records_error_and_degrades() {
        var registry = new SimpleMeterRegistry();
        var metrics = new DramaMetrics(registry, null, null);
        var fake = new FakeRunner();
        fake.throwOnRun = true;
        var provider = new HtmlRenderVideoProvider(fake, metrics);
        provider.setEngineConfig("hyperframes");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.CHROMIUM, provider.resolveEngine());
        assertThat(registry.counter("dramafactory_hyperframes_version_checks_total", "result", "error").count()).isEqualTo(1.0);
    }

    @Test
    void resolveEngine_without_metrics_still_degrades_without_npe() {
        var fake = new FakeRunner();
        fake.exitCode = 3;
        var provider = new HtmlRenderVideoProvider(fake);
        provider.setEngineConfig("hyperframes");

        assertEquals(HtmlRenderVideoProvider.RenderEngine.CHROMIUM, provider.resolveEngine());
    }
}
