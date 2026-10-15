package com.dramafactory.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.VideoProviderRouter;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.lang.reflect.Field;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 针对 {@link VideoTaskService#awaitPollCompletion()} 关闭收尾超时分支的覆盖测试。
 * 仅新增测试文件，不修改任何生产代码。
 */
class VideoTaskServiceTimeoutTest {

    @TempDir
    Path tempDir;

    @Mock
    private VideoTaskRepository videoTaskRepository;
    @Mock
    private ShotRepository shotRepository;
    @Mock
    private FfmpegService ffmpegService;
    @Mock
    private ApplicationContext applicationContext;
    @Mock
    private EpisodeStatusFlowService episodeStatusFlowService;
    @Mock
    private Environment environment;
    @Mock
    private VideoProviderRouter router;

    private VideoTaskService service;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
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
                tempDir.toString()
        );
    }

    private AtomicBoolean pollInFlightFlag() throws Exception {
        Field f = VideoTaskService.class.getDeclaredField("pollInFlight");
        f.setAccessible(true);
        return (AtomicBoolean) f.get(service);
    }

    /**
     * 本测试耗时约 25 秒，覆盖生产代码的 25 秒超时收尾路径。
     * 覆盖分支：
     *  - 第 224 行 while 循环的"超时退出"臂（System.currentTimeMillis() < deadline 为 false）
     *  - 第 233 行 if (pollInFlight.get()) 为 true 的"仍在途→打超时 warn 日志"臂
     * 做法：反射把 pollInFlight 置 true，在子线程调用 awaitPollCompletion()，
     * 主线程 join 等待其自然返回（约 25 秒），断言线程结束且未抛异常。
     */
    @Test
    @Timeout(60)
    void awaitPollCompletion_timeoutAfter25s_logsWarning() throws Exception {
        // 将 pollInFlight 置为 true，模拟关闭时仍有在途轮询任务。
        AtomicBoolean flag = pollInFlightFlag();
        flag.set(true);

        final Throwable[] thrown = new Throwable[1];
        Thread worker = new Thread(() -> {
            try {
                service.awaitPollCompletion();
            } catch (Throwable t) {
                thrown[0] = t;
            }
        }, "await-poll-completion-timeout-test");
        worker.setDaemon(true);
        worker.start();

        // 等待其自然返回（约 25 秒后超时放弃等待）。
        worker.join(40_000L);

        assertTrue(!worker.isAlive(), "awaitPollCompletion 应在 25 秒超时后自然返回");
        assertTrue(thrown[0] == null, "awaitPollCompletion 不应抛出异常，但抛出：" + thrown[0]);
    }
}