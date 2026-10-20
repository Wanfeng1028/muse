package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.RateLimitedException;
import com.dramafactory.service.video.VideoProvider;
import com.dramafactory.service.video.VideoProviderRouter;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;


import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class VideoTaskServiceTest {

    @TempDir
    Path tempDir;

    private VideoTaskRepository videoTaskRepository;
    private ShotRepository shotRepository;
    private FfmpegService ffmpegService;
    private ApplicationContext applicationContext;
    private EpisodeStatusFlowService episodeStatusFlowService;
    private Environment environment;
    private VideoProvider mockProvider;
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
        mockProvider = mock(VideoProvider.class);
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
                3,
                tempDir.toString(),
                dramaMetrics
        );
    }

    private void stubMockProvider() {
        when(applicationContext.getBean("mockVideoProvider", VideoProvider.class)).thenReturn(mockProvider);
        when(router.providerFor(anyString())).thenReturn(mockProvider);
        when(router.submit(any(Shot.class), anyInt())).thenAnswer(inv ->
                new VideoProviderRouter.RouteResult("mock",
                        mockProvider.submit(inv.getArgument(0), inv.getArgument(1)), null, null));
    }

    private Episode newEpisode() {
        Episode e = new Episode();
        e.setId(7L);
        e.setEpisodeNo(3);
        return e;
    }

    private Shot newShot(Long id, int durationSeconds) {
        Shot s = new Shot();
        s.setId(id);
        s.setShotNo(1);
        s.setEpisode(newEpisode());
        s.setDurationSeconds(durationSeconds);
        return s;
    }

    private VideoTask newTask(Long id, Shot shot, VideoTaskStatus status, int attempts) {
        VideoTask t = new VideoTask();
        t.setId(id);
        t.setShot(shot);
        t.setStatus(status);
        t.setAttempts(attempts);
        return t;
    }

    // ==================== A. computeBackoffMs ====================

    @Test
    void a1_backoff_attempts0() {
        assertEquals(10000L, VideoTaskService.computeBackoffMs(0));
    }

    @Test
    void a2_backoff_attempts1() {
        assertEquals(20000L, VideoTaskService.computeBackoffMs(1));
    }

    @Test
    void a3_backoff_attempts2() {
        assertEquals(40000L, VideoTaskService.computeBackoffMs(2));
    }

    @Test
    void a4_backoff_attempts5() {
        assertEquals(320000L, VideoTaskService.computeBackoffMs(5));
    }

    @Test
    void a5_backoff_attempts6() {
        assertEquals(600000L, VideoTaskService.computeBackoffMs(6));
    }

    @Test
    void a6_backoff_attempts7() {
        assertEquals(600000L, VideoTaskService.computeBackoffMs(7));
    }

    @Test
    void a7_backoff_attempts100() {
        assertEquals(600000L, VideoTaskService.computeBackoffMs(100));
    }

    // ==================== B. submit ====================

    @Test
    void b1_submit_idempotent_existingPending() {
        Shot s = newShot(11L, 5);
        VideoTask existing = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(eq(11L), any()))
                .thenReturn(Optional.of(existing));

        Records.SubmitOutcome outcome = service.submit(11L);

        assertFalse(outcome.created());
        assertEquals(21L, outcome.task().id());
    }

    @Test
    void b2_submit_shotNotFound() {
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(eq(99L), any()))
                .thenReturn(Optional.empty());
        when(shotRepository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> service.submit(99L));
    }

    @Test
    void b3_submit_createsNew() {
        Shot s = newShot(11L, 5);
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(eq(11L), any()))
                .thenReturn(Optional.empty());
        when(shotRepository.findById(11L)).thenReturn(Optional.of(s));
        when(videoTaskRepository.save(any(VideoTask.class))).thenAnswer(inv -> {
            VideoTask t = inv.getArgument(0);
            if (t.getId() == null) {
                t.setId(21L);
            }
            return t;
        });

        Records.SubmitOutcome outcome = service.submit(11L);

        assertTrue(outcome.created());
        assertEquals(VideoTaskStatus.PENDING, outcome.task().status());
        assertEquals(0, outcome.task().attempts());
        assertEquals("mock", outcome.task().provider());
    }

    // ==================== C. submitAllForEpisode ====================

    @Test
    void c1_submitAll_twoShots() {
        Shot s1 = newShot(11L, 5);
        Shot s2 = newShot(12L, 5);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s1, s2));
        when(videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(any(), any()))
                .thenReturn(Optional.empty());
        when(shotRepository.findById(11L)).thenReturn(Optional.of(s1));
        when(shotRepository.findById(12L)).thenReturn(Optional.of(s2));
        when(videoTaskRepository.save(any(VideoTask.class))).thenAnswer(inv -> {
            VideoTask t = inv.getArgument(0);
            if (t.getId() == null) {
                t.setId(100L + t.getShot().getId());
            }
            return t;
        });

        List<Records.VideoTaskResponse> result = service.submitAllForEpisode(7L);

        assertEquals(2, result.size());
    }

    @Test
    void c2_submitAll_empty() {
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of());

        List<Records.VideoTaskResponse> result = service.submitAllForEpisode(7L);

        assertTrue(result.isEmpty());
    }

    // ==================== D. retry ====================

    @Test
    void d1_retry_notFound() {
        when(videoTaskRepository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> service.retry(99L));
    }

    @Test
    void d2_retry_pendingRejected() {
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        when(videoTaskRepository.findById(21L)).thenReturn(Optional.of(t));

        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> service.retry(21L));
        assertTrue(ex.getMessage().contains("只有 FAILED 状态的任务才能重试"));
    }

    @Test
    void d3_retry_failedReset() {
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.FAILED, 3);
        t.setErrorMessage("old");
        when(videoTaskRepository.findById(21L)).thenReturn(Optional.of(t));
        when(videoTaskRepository.save(any(VideoTask.class))).thenAnswer(inv -> inv.getArgument(0));

        Records.VideoTaskResponse resp = service.retry(21L);

        assertEquals(VideoTaskStatus.PENDING, resp.status());
        assertEquals(0, resp.attempts());
        assertNull(resp.errorMessage());
        assertNotNull(resp.nextRetryAt());
    }

    // ==================== E. get / listByShot ====================

    @Test
    void e1_get_notFound() {
        when(videoTaskRepository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> service.get(99L));
    }

    @Test
    void e2_get_localPathNull_hasLocalFileFalse() {
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.DONE, 1);
        t.setLocalPath(null);
        when(videoTaskRepository.findById(21L)).thenReturn(Optional.of(t));

        assertFalse(service.get(21L).hasLocalFile());
    }

    @Test
    void e3_get_localFileExists_hasLocalFileTrue() throws Exception {
        Path file = tempDir.resolve("existing.mp4");
        Files.writeString(file, "data");
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.DONE, 1);
        t.setLocalPath(file.toString());
        when(videoTaskRepository.findById(21L)).thenReturn(Optional.of(t));

        assertTrue(service.get(21L).hasLocalFile());
    }

    @Test
    void e4_listByShot_two() {
        Shot s = newShot(11L, 5);
        VideoTask t1 = newTask(21L, s, VideoTaskStatus.DONE, 1);
        VideoTask t2 = newTask(22L, s, VideoTaskStatus.PENDING, 0);
        when(videoTaskRepository.findByShotIdOrderByIdDesc(11L)).thenReturn(List.of(t1, t2));

        List<Records.VideoTaskResponse> result = service.listByShot(11L);

        assertEquals(2, result.size());
    }

    // ==================== F. processDueTasks ====================

    private void stubDue(VideoTask t) {
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(any(), any()))
                .thenReturn(List.of(t));
        when(videoTaskRepository.save(any(VideoTask.class))).thenAnswer(inv -> inv.getArgument(0));
    }

    @Test
    void f1_processDue_empty() {
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(any(), any()))
                .thenReturn(List.of());

        service.processDueTasks();

        verify(videoTaskRepository, never()).save(any());
    }

    @Test
    void f2_processDue_submit_nullDuration_defaults5() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        s.setDurationSeconds(null);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        stubDue(t);
        when(mockProvider.submit(s, 5)).thenReturn("prov-1");

        service.processDueTasks();

        assertEquals(VideoTaskStatus.PROCESSING, t.getStatus());
        assertEquals("prov-1", t.getProviderTaskId());
        assertNotNull(t.getNextRetryAt());
        verify(mockProvider).submit(s, 5);
    }

    @Test
    void f3_processDue_submit_duration8() {
        stubMockProvider();
        Shot s = newShot(11L, 8);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        stubDue(t);
        when(mockProvider.submit(s, 8)).thenReturn("prov-1");

        service.processDueTasks();

        verify(mockProvider).submit(s, 8);
    }

    @Test
    void f4_processDue_rateLimited_45() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        stubDue(t);
        when(mockProvider.submit(s, 5)).thenThrow(new RateLimitedException("限流", 45));

        LocalDateTime before = LocalDateTime.now();
        service.processDueTasks();

        assertEquals(VideoTaskStatus.PENDING, t.getStatus());
        assertNotNull(t.getNextRetryAt());
        assertTrue(t.getNextRetryAt().isAfter(before.plusSeconds(40)));
        assertTrue(t.getNextRetryAt().isBefore(before.plusSeconds(50)));
    }

    @Test
    void f5_processDue_rateLimited_5_floorTo30() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        stubDue(t);
        when(mockProvider.submit(s, 5)).thenThrow(new RateLimitedException("限流", 5));

        LocalDateTime before = LocalDateTime.now();
        service.processDueTasks();

        assertEquals(VideoTaskStatus.PENDING, t.getStatus());
        assertNotNull(t.getNextRetryAt());
        assertTrue(t.getNextRetryAt().isAfter(before.plusSeconds(25)));
        assertTrue(t.getNextRetryAt().isBefore(before.plusSeconds(35)));
    }

    @Test
    void f6_processDue_runtimeException_attempts0_to1() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        stubDue(t);
        when(mockProvider.submit(s, 5)).thenThrow(new RuntimeException("boom"));

        service.processDueTasks();

        assertEquals(1, t.getAttempts());
        assertEquals(VideoTaskStatus.PENDING, t.getStatus());
        assertEquals("boom", t.getErrorMessage());
    }

    @Test
    void f7_processDue_runtimeException_attempts2_to3_failed() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 2);
        stubDue(t);
        when(mockProvider.submit(s, 5)).thenThrow(new RuntimeException("boom"));

        service.processDueTasks();

        assertEquals(3, t.getAttempts());
        assertEquals(VideoTaskStatus.FAILED, t.getStatus());
    }

    @Test
    void f8_processDue_pollCompleted() throws Exception {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.COMPLETED, "mock://clip?seconds=4", null, 100));
        doNothing().when(ffmpegService).generateTestClip(any(), anyInt());

        service.processDueTasks();

        assertEquals(VideoTaskStatus.DONE, t.getStatus());
        assertNotNull(t.getLocalPath());
        assertTrue(t.getLocalPath().startsWith(tempDir.resolve("videos").toString()));
        assertEquals("mock://clip?seconds=4", t.getVideoUrl());
        verify(ffmpegService).generateTestClip(any(), eq(4));
        verify(episodeStatusFlowService).refreshAfterTaskDone(7L);
    }

    @Test
    void f9_processDue_pollCompleted_badSeconds_fallback5() throws Exception {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.COMPLETED, "mock://clip?seconds=abc", null, 100));
        doNothing().when(ffmpegService).generateTestClip(any(), anyInt());

        service.processDueTasks();

        verify(ffmpegService).generateTestClip(any(), eq(5));
    }

    @Test
    void f10_processDue_pollCompleted_noSeconds_fallback5() throws Exception {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.COMPLETED, "mock://clip", null, 100));
        doNothing().when(ffmpegService).generateTestClip(any(), anyInt());

        service.processDueTasks();

        verify(ffmpegService).generateTestClip(any(), eq(5));
    }

    @Test
    void f11_processDue_pollCompleted_ampTruncate() throws Exception {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.COMPLETED, "mock://clip?seconds=4&x=1", null, 100));
        doNothing().when(ffmpegService).generateTestClip(any(), anyInt());

        service.processDueTasks();

        verify(ffmpegService).generateTestClip(any(), eq(4));
    }

    @Test
    void f12_processDue_refreshThrows_stillDone() throws Exception {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.COMPLETED, "mock://clip?seconds=4", null, 100));
        doNothing().when(ffmpegService).generateTestClip(any(), anyInt());
        doThrow(new RuntimeException("refresh-fail"))
                .when(episodeStatusFlowService).refreshAfterTaskDone(7L);

        service.processDueTasks();

        assertEquals(VideoTaskStatus.DONE, t.getStatus());
    }

    @Test
    void f13_processDue_pollFailed() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.FAILED, null, "boom", 0));

        service.processDueTasks();

        assertEquals(2, t.getAttempts());
        assertEquals("boom", t.getErrorMessage());
        assertEquals(VideoTaskStatus.PROCESSING, t.getStatus());
    }

    @Test
    void f14_processDue_pollFailed_nullError() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.FAILED, null, null, 0));

        service.processDueTasks();

        assertEquals(2, t.getAttempts());
        assertNull(t.getErrorMessage());
    }

    @Test
    void f15_processDue_pollQueued_updatesNextRetryAt() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        t.setNextRetryAt(LocalDateTime.now().minusMinutes(1));
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.QUEUED, null, null, 10));

        LocalDateTime before = LocalDateTime.now();
        service.processDueTasks();

        assertEquals(VideoTaskStatus.PROCESSING, t.getStatus());
        assertNotNull(t.getNextRetryAt());
        assertTrue(t.getNextRetryAt().isAfter(before));
    }

    @Test
    void f16_processDue_pollCompleted_httpLoopback_fails() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.COMPLETED, "http://127.0.0.1:9/x", null, 100));

        service.processDueTasks();

        assertFalse(t.getStatus() == VideoTaskStatus.DONE);
        assertEquals(2, t.getAttempts());
        assertNotNull(t.getErrorMessage());
    }

    @Test
    void f17_processDue_pollCompleted_nullUrl_fails() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 1);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.COMPLETED, null, null, 100));

        service.processDueTasks();

        assertFalse(t.getStatus() == VideoTaskStatus.DONE);
        assertEquals(2, t.getAttempts());
    }

    // ==================== G. awaitPollCompletion ====================

    @Test
    void g1_awaitPollCompletion_noInflight() {
        assertDoesNotThrow(() -> service.awaitPollCompletion());
    }

    // ==================== H. 覆盖率补遗 ====================

    private AtomicBoolean pollInFlightFlag() throws Exception {
        Field f = VideoTaskService.class.getDeclaredField("pollInFlight");
        f.setAccessible(true);
        return (AtomicBoolean) f.get(service);
    }

    @Test
    void h1_router_submit_agnes_noFallback() {
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        stubDue(t);
        when(router.submit(s, 5)).thenReturn(new VideoProviderRouter.RouteResult("agnes", "a1", null, null));

        service.processDueTasks();

        assertEquals(VideoTaskStatus.PROCESSING, t.getStatus());
        assertEquals("agnes", t.getProvider());
        assertEquals("a1", t.getProviderTaskId());
        assertNull(t.getFallbackReason());
    }

    @Test
    void h2_router_submit_fallback_qwen_recordsReason() {
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PENDING, 0);
        stubDue(t);
        when(router.submit(s, 5)).thenReturn(
                new VideoProviderRouter.RouteResult("qwen", "q1", "限流(429)，60秒后可重试", null));

        service.processDueTasks();

        assertEquals(VideoTaskStatus.PROCESSING, t.getStatus());
        assertEquals("qwen", t.getProvider());
        assertEquals("q1", t.getProviderTaskId());
        assertEquals("限流(429)，60秒后可重试", t.getFallbackReason());
    }

    @Test
    void h3_poll_processing_result_updatesNextRetry() {
        stubMockProvider();
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.PROCESSING, 0);
        t.setProviderTaskId("p1");
        stubDue(t);
        when(mockProvider.poll("p1")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.PROCESSING, null, null, 30));

        service.processDueTasks();

        assertEquals(VideoTaskStatus.PROCESSING, t.getStatus());
        assertNotNull(t.getNextRetryAt());
    }

    @Test
    void h4_toResponse_missingLocalFile() {
        Shot s = newShot(11L, 5);
        VideoTask t = newTask(21L, s, VideoTaskStatus.DONE, 1);
        t.setLocalPath(tempDir.resolve("gone.mp4").toString());
        when(videoTaskRepository.findById(21L)).thenReturn(Optional.of(t));

        Records.VideoTaskResponse resp = service.get(21L);

        assertEquals(Boolean.FALSE, resp.hasLocalFile());
    }

    @Test
    void h5_awaitPollCompletion_inflight_completes() throws Exception {
        AtomicBoolean inFlight = pollInFlightFlag();
        inFlight.set(true);
        Thread t = new Thread(() -> service.awaitPollCompletion());
        t.start();
        Thread.sleep(500);
        inFlight.set(false);
        t.join(5000);

        assertFalse(t.isAlive());
    }

    @Test
    void h6_awaitPollCompletion_interrupted() throws Exception {
        AtomicBoolean inFlight = pollInFlightFlag();
        inFlight.set(true);
        Thread t = new Thread(() -> service.awaitPollCompletion());
        t.start();
        Thread.sleep(150);
        t.interrupt();
        t.join(5000);
        inFlight.set(false);

        assertFalse(t.isAlive());
    }
}
