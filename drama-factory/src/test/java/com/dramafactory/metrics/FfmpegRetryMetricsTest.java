package com.dramafactory.metrics;

import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * v2.29 flaky 根因歼灭新增指标的单元测试：ffmpeg 重试计数与轮询跳过计数。
 */
class FfmpegRetryMetricsTest {

    private SimpleMeterRegistry registry;
    private DramaMetrics dramaMetrics;

    @BeforeEach
    void setUp() {
        RunRepository runRepository = mock(RunRepository.class);
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        when(runRepository.countByStatus(any())).thenReturn(0L);
        when(videoTaskRepository.countByStatus(any())).thenReturn(0L);
        registry = new SimpleMeterRegistry();
        dramaMetrics = new DramaMetrics(registry, runRepository, videoTaskRepository);
    }

    @Test
    void recordFfmpegRetry_countsByOperationKindAndResult() {
        dramaMetrics.recordFfmpegRetry("concat", true, true);
        dramaMetrics.recordFfmpegRetry("concat", true, true);
        dramaMetrics.recordFfmpegRetry("concat", true, false);
        dramaMetrics.recordFfmpegRetry("burn-subtitles", false, false);
        dramaMetrics.recordFfmpegRetry(null, true, true);

        assertEquals(2.0, registry.counter("dramafactory_ffmpeg_retries_total",
                "operation", "concat", "kind", "transient", "result", "ok").count());
        assertEquals(1.0, registry.counter("dramafactory_ffmpeg_retries_total",
                "operation", "concat", "kind", "transient", "result", "error").count());
        assertEquals(1.0, registry.counter("dramafactory_ffmpeg_retries_total",
                "operation", "burn-subtitles", "kind", "permanent", "result", "error").count());
        assertEquals(1.0, registry.counter("dramafactory_ffmpeg_retries_total",
                "operation", "unknown", "kind", "transient", "result", "ok").count());
    }

    @Test
    void recordPollSkipped_counts() {
        dramaMetrics.recordPollSkipped();
        dramaMetrics.recordPollSkipped();
        dramaMetrics.recordPollSkipped();
        assertEquals(3.0, registry.counter("dramafactory_video_poll_skipped_total").count());
    }
}
