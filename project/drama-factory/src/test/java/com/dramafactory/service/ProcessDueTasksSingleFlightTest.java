package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.VideoProvider;
import com.dramafactory.service.video.VideoProviderRouter;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * v2.29 flaky 根因歼灭——{@link VideoTaskService#processDueTasks()} 单飞（single-flight）保护的并发回归测试。
 *
 * <p>背景：调度器可能在同一时刻因多重触发（定时 + 手动/多实例竞争）并发进入 {@code processDueTasks()}。
 * 若缺少单飞保护，同一个到期任务会被重复 submit 到真实 provider，造成重复计费与孤儿任务。
 * b3 批在方法入口加入 {@code pollInFlight.compareAndSet(false, true)} 保护：
 * 只有第一个进入者真正执行轮询，其余并发调用立即 return 并调用
 * {@link DramaMetrics#recordPollSkipped()} 计数。</p>
 *
 * <p>本测试通过让 provider.submit 阻塞，人为制造“线程 A 仍在执行中”的时间窗口，
 * 在此窗口内由主线程再次调用 {@code processDueTasks()}，验证：</p>
 * <ul>
 *   <li>{@code router.submit(...)} 只被调用 1 次（无重复提交，杜绝重复计费/孤儿任务）；</li>
 *   <li>{@link DramaMetrics#recordPollSkipped()} 恰好被调用 1 次（跳过被正确计数）。</li>
 * </ul>
 *
 * <p>并发测试全部带超时兜底（latch await 超时、thread join 超时、{@code @Timeout}），绝不无限等待。</p>
 */
class ProcessDueTasksSingleFlightTest {

    @TempDir
    Path tempDir;

    @Test
    @Timeout(value = 60, unit = TimeUnit.SECONDS)
    void concurrentCallsSubmitOnlyOnce() throws Exception {
        // mocks
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        ShotRepository shotRepository = mock(ShotRepository.class);
        FfmpegService ffmpegService = mock(FfmpegService.class);
        ApplicationContext applicationContext = mock(ApplicationContext.class);
        EpisodeStatusFlowService episodeStatusFlowService = mock(EpisodeStatusFlowService.class);
        Environment environment = mock(Environment.class);
        VideoProviderRouter router = mock(VideoProviderRouter.class);
        DramaMetrics dramaMetrics = mock(DramaMetrics.class);

        VideoTaskService service = new VideoTaskService(videoTaskRepository, shotRepository,
                ffmpegService, applicationContext, episodeStatusFlowService, environment,
                router, "mock", 10000L, 8, tempDir.toString(), dramaMetrics);

        // 一个 PENDING 到期任务
        Shot shot = mock(Shot.class);
        when(shot.getDurationSeconds()).thenReturn(2);
        VideoTask task = new VideoTask();
        task.setId(1L);
        task.setShot(shot);
        task.setStatus(VideoTaskStatus.PENDING);
        task.setAttempts(0);
        task.setNextRetryAt(LocalDateTime.now().minusSeconds(5));
        when(videoTaskRepository.findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(
                eq(List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING)), any(LocalDateTime.class)))
                .thenReturn(List.of(task));

        // router.submit 阻塞 3 秒，制造"线程 A 仍在执行中"的时间窗口
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        when(router.submit(any(Shot.class), anyInt())).thenAnswer(inv -> {
            entered.countDown();
            assertTrue(release.await(10, TimeUnit.SECONDS), "submit 不应被卡住超过 10 秒");
            return new VideoProviderRouter.RouteResult("mock", "mock-task-1", null, null);
        });

        AtomicReference<Throwable> errorA = new AtomicReference<>();
        Thread threadA = new Thread(() -> {
            try {
                service.processDueTasks();
            } catch (Throwable t) {
                errorA.set(t);
            }
        }, "poll-thread-A");
        threadA.start();
        assertTrue(entered.await(10, TimeUnit.SECONDS), "线程 A 应已进入 submit");

        // 线程 A 仍在执行中时，主线程再调一次：应被单飞跳过
        service.processDueTasks();

        release.countDown();
        threadA.join(15000);
        assertNull(errorA.get(), "线程 A 不应抛异常：" + errorA.get());

        // 断言：provider.submit 只被调用 1 次（无重复提交）；跳过被计数 1 次
        verify(router, timeout(10000).times(1)).submit(any(Shot.class), anyInt());
        verify(dramaMetrics, timeout(10000).times(1)).recordPollSkipped();
    }
}
