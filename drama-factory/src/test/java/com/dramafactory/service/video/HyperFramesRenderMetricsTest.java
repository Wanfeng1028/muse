package com.dramafactory.service.video;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Shot;
import com.dramafactory.service.video.HyperFramesVideoProvider.CommandRunner;
import com.dramafactory.service.video.HyperFramesVideoProvider.CommandRunner.ExecResult;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.assertj.core.data.Offset;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

import static org.assertj.core.api.Assertions.assertThat;

class HyperFramesRenderMetricsTest {

    private static void setField(Object target, String name, Object value) {
        try {
            var f = target.getClass().getDeclaredField(name);
            f.setAccessible(true);
            f.set(target, value);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static void awaitUntil(long deadlineMs, BooleanSupplier condition) {
        while (System.currentTimeMillis() < deadlineMs) {
            if (condition.getAsBoolean()) return;
            try {
                Thread.sleep(50);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new RuntimeException(e);
            }
        }
        throw new AssertionError("Await timed out");
    }

    @Test
    void record_ok() {
        var registry = new SimpleMeterRegistry();
        var metrics = new DramaMetrics(registry, null, null);
        metrics.recordHyperFramesRender("shot-card", 150, true);

        var counter = registry.counter("dramafactory_hyperframes_renders_total", "template", "shot-card", "result", "ok");
        var timer = registry.timer("dramafactory_hyperframes_render_duration", "template", "shot-card");

        assertThat(counter.count()).isEqualTo(1.0);
        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isCloseTo(150.0, Offset.offset(1.0));
    }

    @Test
    void record_normalization() {
        var registry = new SimpleMeterRegistry();
        var metrics = new DramaMetrics(registry, null, null);
        metrics.recordHyperFramesRender(null, -5, false);
        metrics.recordHyperFramesRender("   ", 0, false);

        var counter = registry.counter("dramafactory_hyperframes_renders_total", "template", "unknown", "result", "error");
        var timer = registry.timer("dramafactory_hyperframes_render_duration", "template", "unknown");

        assertThat(counter.count()).isEqualTo(2.0);
        assertThat(timer.count()).isEqualTo(2);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(0.0);
    }

    @Test
    void provider_success_records_ok(@TempDir Path tempDir) {
        var registry = new SimpleMeterRegistry();
        var metrics = new DramaMetrics(registry, null, null);

        CommandRunner runner = (command, workDir, timeoutSeconds) -> {
            if (command.contains("--version")) {
                return new ExecResult(0, "v1.0");
            }
            Files.createDirectories(workDir.resolve("out"));
            Files.createFile(workDir.resolve("out/video.mp4"));
            return new ExecResult(0, "done");
        };

        var provider = new HyperFramesVideoProvider(runner, metrics);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);
        setField(provider, "template", "shot-card");

        var shot = new Shot();
        shot.setDescription("test shot");
        String taskId = provider.submit(shot, 6);

        long deadline = System.currentTimeMillis() + 5000;
        awaitUntil(deadline, () ->
                registry.counter("dramafactory_hyperframes_renders_total", "template", "shot-card", "result", "ok").count() >= 1.0
        );

        assertThat(provider.poll(taskId).status()).isEqualTo(VideoProvider.RemoteStatus.COMPLETED);
    }

    @Test
    void provider_failure_records_error(@TempDir Path tempDir) {
        var registry = new SimpleMeterRegistry();
        var metrics = new DramaMetrics(registry, null, null);

        CommandRunner runner = (command, workDir, timeoutSeconds) -> {
            if (command.contains("--version")) {
                return new ExecResult(0, "v1.0");
            }
            return new ExecResult(1, "failed");
        };

        var provider = new HyperFramesVideoProvider(runner, metrics);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);
        setField(provider, "template", "shot-timeline");

        var shot = new Shot();
        shot.setDescription("test shot");
        String taskId = provider.submit(shot, 6);

        long deadline = System.currentTimeMillis() + 5000;
        awaitUntil(deadline, () ->
                registry.counter("dramafactory_hyperframes_renders_total", "template", "shot-timeline", "result", "error").count() >= 1.0
        );

        assertThat(provider.poll(taskId).status()).isEqualTo(VideoProvider.RemoteStatus.FAILED);
    }

    @Test
    void provider_without_metrics_still_renders(@TempDir Path tempDir) {
        CommandRunner runner = (command, workDir, timeoutSeconds) -> {
            if (command.contains("--version")) {
                return new ExecResult(0, "v1.0");
            }
            Files.createDirectories(workDir.resolve("out"));
            Files.createFile(workDir.resolve("out/video.mp4"));
            return new ExecResult(0, "done");
        };

        var provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);

        var shot = new Shot();
        shot.setDescription("test shot");
        String taskId = provider.submit(shot, 6);

        long deadline = System.currentTimeMillis() + 5000;
        awaitUntil(deadline, () ->
                provider.poll(taskId).status() == VideoProvider.RemoteStatus.COMPLETED
        );
    }
}