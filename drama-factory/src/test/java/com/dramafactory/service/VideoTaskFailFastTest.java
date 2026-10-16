package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.VideoProvider;
import com.dramafactory.service.video.VideoProviderRouter;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * v2.29 flaky 根因歼灭：验证永久失败 fail fast、瞬时失败保持指数退避的语义。
 *
 * <p>永久 ffmpeg 失败（FfmpegException.isTransient()==false）→ 直接 FAILED，不再重试；
 * 瞬时 ffmpeg 失败（isTransient()==true）→ 保持 PROCESSING 并按退避安排下次重试。</p>
 */
class VideoTaskFailFastTest {

    @TempDir
    Path tempDir;

    private VideoTaskRepository videoTaskRepository;
    private ShotRepository shotRepository;
    private FfmpegService ffmpegService;
    private ApplicationContext applicationContext;
    private EpisodeStatusFlowService episodeStatusFlowService;
    private Environment environment;
    private VideoProviderRouter router;
    private DramaMetrics dramaMetrics;
    private VideoTaskService service;

    @BeforeEach
    void setUp() {
        videoTaskRepository = mock(VideoTaskRepository.class);
        shotRepository = mock(ShotRepository.class);
        ffmpegService = mock(FfmpegService.class);
        applicationContext = mock(ApplicationContext.class);
        episodeStatusFlowService = mock(EpisodeStatusFlowService.class);
        environment = mock(Environment.class);
        router = mock(VideoProviderRouter.class);
        dramaMetrics = mock(DramaMetrics.class);

        service = new VideoTaskService(
                videoTaskRepository,
                shotRepository,
                ffmpegService,
                applicationContext,
                episodeStatusFlowService,
                environment,
                router,
                "mock",
                10000L,
                8,
                tempDir.toString(),
                dramaMetrics);
    }

    private VideoTask processingTask() {
        Shot shot = mock(Shot.class);
        VideoTask task = new VideoTask();
        task.setId(1L);
        task.setShot(shot);
        task.setStatus(VideoTaskStatus.PROCESSING);
        task.setProvider("mock");
        task.setProviderTaskId("mock-task-1");
        task.setAttempts(0);
        task.setNextRetryAt(LocalDateTime.now().minusSeconds(5));
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(
                eq(List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)), any(LocalDateTime.class)))
                .thenReturn(List.of(task));
        VideoProvider mockProvider = mock(VideoProvider.class);
        when(router.providerFor("mock")).thenReturn(mockProvider);
        when(mockProvider.poll("mock-task-1")).thenReturn(
                new VideoProvider.ProbeResult(VideoProvider.RemoteStatus.COMPLETED, "mock://clip?seconds=2", null, 100));
        return task;
    }

    @Test
    void permanentFfmpegFailureMarksFailedImmediately() {
        VideoTask task = processingTask();
        doThrow(new FfmpegService.FfmpegException("无法启动命令: ffmpeg", false))
                .when(ffmpegService).generateTestClip(any(Path.class), anyInt());

        service.processDueTasks();

        assertEquals(VideoTaskStatus.FAILED, task.getStatus(), "永久失败应直接 FAILED");
        assertEquals(1, task.getAttempts());
        assertTrue(task.getErrorMessage() != null && task.getErrorMessage().contains("永久失败"),
                "错误信息应标明永久失败，实际：" + task.getErrorMessage());
        verify(ffmpegService, times(1)).generateTestClip(any(Path.class), anyInt());
        verify(episodeStatusFlowService, never()).refreshAfterTaskDone(anyLong());
    }

    @Test
    void transientFfmpegFailureKeepsBackoff() {
        VideoTask task = processingTask();
        doThrow(new FfmpegService.FfmpegException("命令超时(120s): ffmpeg", true))
                .when(ffmpegService).generateTestClip(any(Path.class), anyInt());

        service.processDueTasks();

        assertEquals(VideoTaskStatus.PROCESSING, task.getStatus(), "瞬时失败应保持 PROCESSING 等待重试");
        assertEquals(1, task.getAttempts());
        assertTrue(task.getNextRetryAt().isAfter(LocalDateTime.now().plusSeconds(15)),
                "瞬时失败应按指数退避安排下次重试（attempts=1 → 20s），实际 nextRetryAt=" + task.getNextRetryAt());
    }
}
