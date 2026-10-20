package com.dramafactory.service;

import com.dramafactory.billing.CostLedgerEntry;
import com.dramafactory.billing.CostLedgerService;
import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Episode;
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
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * VideoTaskService 账本集成相关测试。
 */
class VideoTaskServiceBillingTest {

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
    private CostLedgerService costLedgerService;

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
        costLedgerService = mock(CostLedgerService.class);
        service = new VideoTaskService(videoTaskRepository, shotRepository, ffmpegService, applicationContext,
                episodeStatusFlowService, environment, router, "mock", 10000L, 3, tempDir.toString(), dramaMetrics,
                costLedgerService);
    }

    private VideoTaskService newServiceWithoutLedger() {
        return new VideoTaskService(videoTaskRepository, shotRepository, ffmpegService, applicationContext,
                episodeStatusFlowService, environment, router, "mock", 10000L, 3, tempDir.toString(), dramaMetrics,
                null);
    }

    private VideoTask pendingTaskWithShot() {
        VideoTask task = new VideoTask();
        task.setId(1L);
        task.setStatus(VideoTaskStatus.PENDING);
        task.setNextRetryAt(LocalDateTime.now().minusSeconds(1));

        Shot shot = mock(Shot.class);
        when(shot.getId()).thenReturn(7L);
        when(shot.getDurationSeconds()).thenReturn(5);
        task.setShot(shot);
        return task;
    }

    private VideoTask processingTask(Long ledgerEntryId) {
        VideoTask task = new VideoTask();
        task.setId(1L);
        task.setStatus(VideoTaskStatus.PROCESSING);
        task.setProvider("mock");
        task.setProviderTaskId("t1");
        task.setLedgerEntryId(ledgerEntryId);
        task.setCreatedAt(LocalDateTime.now());
        task.setNextRetryAt(LocalDateTime.now().minusSeconds(1));

        Shot shot = mock(Shot.class);
        when(shot.getId()).thenReturn(7L);
        Episode episode = mock(Episode.class);
        when(episode.getId()).thenReturn(3L);
        when(shot.getEpisode()).thenReturn(episode);
        task.setShot(shot);
        return task;
    }

    @Test
    void submitTaskPersistsLedgerEntryIdFromRouteResult() {
        VideoTask task = pendingTaskWithShot();
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(anyList(), any()))
                .thenReturn(List.of(task));
        when(router.submit(any(), eq(5)))
                .thenReturn(new VideoProviderRouter.RouteResult("mock", "t1", null, 77L));

        service.processDueTasks();

        assertEquals(77L, task.getLedgerEntryId());
        assertEquals(VideoTaskStatus.PROCESSING, task.getStatus());
    }

    @Test
    void pollCompletedSettlesLedgerAndClearsEntryId() throws Exception {
        VideoTask task = processingTask(55L);
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(anyList(), any()))
                .thenReturn(List.of(task));

        VideoProvider mockProvider = mock(VideoProvider.class);
        when(router.providerFor("mock")).thenReturn(mockProvider);
        when(mockProvider.poll(anyString()))
                .thenReturn(new VideoProvider.ProbeResult(VideoProvider.RemoteStatus.COMPLETED,
                        "mock://x?seconds=5", null, 100));

        doNothing().when(ffmpegService).generateTestClip(any(), anyInt());

        CostLedgerEntry entry = mock(CostLedgerEntry.class);
        when(entry.getEstimatedUsd()).thenReturn(0.4);
        when(costLedgerService.requireEntry(55L)).thenReturn(entry);

        service.processDueTasks();

        verify(costLedgerService).complete(eq(55L), eq(0.4), anyLong());
        assertNull(task.getLedgerEntryId());
    }

    @Test
    void pollFailedSettlesLedgerAndClearsEntryId() {
        VideoTask task = processingTask(55L);
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(anyList(), any()))
                .thenReturn(List.of(task));

        VideoProvider mockProvider = mock(VideoProvider.class);
        when(router.providerFor("mock")).thenReturn(mockProvider);
        when(mockProvider.poll(anyString()))
                .thenReturn(new VideoProvider.ProbeResult(VideoProvider.RemoteStatus.FAILED, null, "boom", 0));

        service.processDueTasks();

        verify(costLedgerService).fail(eq(55L), eq(0d), anyLong(),
                argThat(note -> note != null && note.contains("boom")));
        assertNull(task.getLedgerEntryId());
    }

    @Test
    void completedWithoutLedgerEntryIdSkipsLedger() throws Exception {
        VideoTask task = processingTask(null);
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(anyList(), any()))
                .thenReturn(List.of(task));

        VideoProvider mockProvider = mock(VideoProvider.class);
        when(router.providerFor("mock")).thenReturn(mockProvider);
        when(mockProvider.poll(anyString()))
                .thenReturn(new VideoProvider.ProbeResult(VideoProvider.RemoteStatus.COMPLETED,
                        "mock://x?seconds=5", null, 100));

        doNothing().when(ffmpegService).generateTestClip(any(), anyInt());

        service.processDueTasks();

        verifyNoInteractions(costLedgerService);
    }

    @Test
    void completedWithNullLedgerServiceDoesNotThrow() throws Exception {
        VideoTaskService serviceWithoutLedger = newServiceWithoutLedger();

        VideoTask task = processingTask(55L);
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(anyList(), any()))
                .thenReturn(List.of(task));

        VideoProvider mockProvider = mock(VideoProvider.class);
        when(router.providerFor("mock")).thenReturn(mockProvider);
        when(mockProvider.poll(anyString()))
                .thenReturn(new VideoProvider.ProbeResult(VideoProvider.RemoteStatus.COMPLETED,
                        "mock://x?seconds=5", null, 100));

        doNothing().when(ffmpegService).generateTestClip(any(), anyInt());

        assertDoesNotThrow(() -> serviceWithoutLedger.processDueTasks());
        assertEquals(VideoTaskStatus.DONE, task.getStatus());
    }
}
