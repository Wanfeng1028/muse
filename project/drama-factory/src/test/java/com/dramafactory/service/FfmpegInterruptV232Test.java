package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * v2.32 flaky-4：关闭 docs/FLAKY_ROOT_CAUSE.md §7 第 4 条残余风险
 * ——"InterruptedException 被重包装为瞬时异常导致任务被重排而非终止"。
 * <p>
 * 验证目标：
 * <ul>
 *   <li>用例 1：{@link FfmpegService#run} 内 {@code process.waitFor} 被中断时抛
 *       {@link FfmpegService.FfmpegInterruptedException}（且 instanceof FfmpegException 成立），
 *       cause 为 {@link InterruptedException}，且 run 的 catch 恢复了中断标志。</li>
 *   <li>用例 2：{@link FinalCutService} 的 withFfmpegRetry 遇专用中断异常直接终止不重试，
 *       concatClips 只被调用 1 次，且未进 transient 指标分支。</li>
 *   <li>用例 3：withFfmpegRetry 内 {@code Thread.sleep} 退避时被中断，抛专用异常且 cause
 *       为 {@link InterruptedException}（修复 cause=null 丢失问题）。</li>
 * </ul>
 * <p>
 * 用例 4（processDueTasks 中断路径）未覆盖：需同时构造 VideoTaskRepository、VideoProviderRouter、
 * FfmpegService、Episode/Shot 链路的 mock 图，mock 链过长、脆弱性高，按 prompt 允许省略并在此注明。
 * 相关行为已由用例 2 通过 withFfmpegRetry 的终止语义间接约束，且 processDueTasks 的 catch 顺序
 * （专用 catch 在 catch(Exception) 之前）由编译期类型层级保证。
 */
class FfmpegInterruptV232Test {

    @TempDir
    Path tempDir;

    private FinalCutRepository finalCutRepository;
    private EpisodeRepository episodeRepository;
    private ShotRepository shotRepository;
    private VideoTaskRepository videoTaskRepository;
    private SubtitleService subtitleService;
    private FfmpegService ffmpegService;
    private EpisodeStatusFlowService episodeStatusFlowService;
    private DramaMetrics dramaMetrics;
    private FinalCutService service;

    @BeforeEach
    void setUp() {
        finalCutRepository = mock(FinalCutRepository.class);
        episodeRepository = mock(EpisodeRepository.class);
        shotRepository = mock(ShotRepository.class);
        videoTaskRepository = mock(VideoTaskRepository.class);
        subtitleService = mock(SubtitleService.class);
        ffmpegService = mock(FfmpegService.class);
        episodeStatusFlowService = mock(EpisodeStatusFlowService.class);
        dramaMetrics = mock(DramaMetrics.class);
        service = new FinalCutService(finalCutRepository, episodeRepository, shotRepository,
                videoTaskRepository, subtitleService, ffmpegService, episodeStatusFlowService,
                tempDir.toString(), dramaMetrics, 3, 2000L);
        when(finalCutRepository.save(any())).thenAnswer(inv -> inv.getArgument(0));
    }

    private Episode episode() {
        Episode e = new Episode();
        e.setId(7L);
        e.setEpisodeNo(3);
        return e;
    }

    private Shot shot(Episode e) {
        Shot s = new Shot();
        s.setId(11L);
        s.setShotNo(1);
        s.setEpisode(e);
        s.setDurationSeconds(5);
        return s;
    }

    private VideoTask doneTask(Shot s, Path clip) {
        VideoTask t = new VideoTask();
        t.setId(21L);
        t.setShot(s);
        t.setStatus(VideoTaskStatus.DONE);
        t.setLocalPath(clip.toString());
        return t;
    }

    /**
     * 用例 1：反射调 private {@code FfmpegService.run(List, long)}，主线程被 interrupt 后
     * 必须抛 {@link FfmpegService.FfmpegInterruptedException}，cause 为 {@link InterruptedException}，
     * 且 run 的 catch 已恢复中断标志（{@code Thread.currentThread().isInterrupted()} 为 true）。
     */
    @Test
    @Timeout(30)
    void run_whenInterrupted_throwsFfmpegInterruptedExceptionAndRestoresFlag() throws Exception {
        FfmpegService svc = new FfmpegService("ffmpeg", "ffprobe");
        Method runMethod = FfmpegService.class.getDeclaredMethod("run", List.class, long.class);
        runMethod.setAccessible(true);

        List<String> cmd = List.of("sh", "-c", "sleep 30; exit 0");
        AtomicReference<Throwable> captured = new AtomicReference<>();
        AtomicReference<Boolean> flagAfter = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                runMethod.invoke(svc, cmd, 60L);
            } catch (InvocationTargetException ite) {
                captured.set(ite.getCause());
            } catch (Throwable t) {
                captured.set(t);
            } finally {
                flagAfter.set(Thread.currentThread().isInterrupted());
            }
        }, "flaky4-run-interrupt-worker");
        worker.start();

        // 给子进程一点启动时间，然后中断 worker
        Thread.sleep(500L);
        worker.interrupt();
        worker.join(15_000L);
        assertTrue(!worker.isAlive(), "worker 应在中断后及时退出，不应挂死");

        Throwable cause = captured.get();
        assertInstanceOf(FfmpegService.FfmpegInterruptedException.class, cause,
                "run 被中断应抛专用 FfmpegInterruptedException，实际: " + cause);
        assertInstanceOf(FfmpegService.FfmpegException.class, cause,
                "FfmpegInterruptedException 必须是 FfmpegException 的子类");
        assertInstanceOf(InterruptedException.class, cause.getCause(),
                "cause 必须是 InterruptedException，实际: " + (cause == null ? null : cause.getCause()));
        assertTrue(Boolean.TRUE.equals(flagAfter.get()),
                "run 的 catch 必须调用 Thread.currentThread().interrupt() 恢复中断标志");
    }

    /**
     * 用例 2：withFfmpegRetry 遇专用中断异常直接终止不重试。
     * 断言：buildFinalCut 抛出专用异常；concatClips 只被调用 1 次（证明未重试）；
     * recordFfmpegRetry 未被调用（证明未进 transient 分支）。
     */
    @Test
    @Timeout(30)
    void withFfmpegRetry_whenInterrupted_terminatesWithoutRetry() throws Exception {
        Episode e = episode();
        Shot s = shot(e);
        Path clip = tempDir.resolve("clip1.mp4");
        Files.createFile(clip);
        VideoTask t = doneTask(s, clip);

        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L)).thenReturn(Optional.of(t));
        when(ffmpegService.probeDurationSeconds(any(Path.class))).thenReturn(5.0);

        doThrow(new FfmpegService.FfmpegInterruptedException(
                "test-interrupted", new InterruptedException("test-interrupt-cause")))
                .when(ffmpegService).concatClips(anyList(), any(Path.class));

        FfmpegService.FfmpegInterruptedException thrown = assertThrows(
                FfmpegService.FfmpegInterruptedException.class,
                () -> service.buildFinalCut(7L));

        assertInstanceOf(InterruptedException.class, thrown.getCause(),
                "专用中断异常必须携带 InterruptedException 作为 cause");
        verify(ffmpegService, times(1)).concatClips(anyList(), any(Path.class));
        verify(dramaMetrics, times(0)).recordFfmpegRetry(any(), any(Boolean.class), any(Boolean.class));
    }

    /**
     * 用例 3：withFfmpegRetry 的 Thread.sleep 退避被中断，抛专用异常且 cause 为 InterruptedException
     * （证明 cause 不再丢失，替代原 (String, boolean) 构造器造成的 cause=null）。
     */
    @Test
    @Timeout(30)
    void withFfmpegRetry_whenSleepInterrupted_throwsInterruptedWithCause() throws Exception {
        Episode e = episode();
        Shot s = shot(e);
        Path clip = tempDir.resolve("clip2.mp4");
        Files.createFile(clip);
        VideoTask t = doneTask(s, clip);

        when(episodeRepository.findById(7L)).thenReturn(Optional.of(e));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(7L)).thenReturn(List.of(s));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(11L)).thenReturn(Optional.of(t));
        when(ffmpegService.probeDurationSeconds(any(Path.class))).thenReturn(5.0);

        // 第一次抛普通 transient FfmpegException → 触发 Thread.sleep(2000) 退避
        doThrow(new FfmpegService.FfmpegException("transient", true))
                .when(ffmpegService).concatClips(anyList(), any(Path.class));

        AtomicReference<Throwable> captured = new AtomicReference<>();
        AtomicReference<Boolean> flagAfter = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                service.buildFinalCut(7L);
            } catch (Throwable t2) {
                captured.set(t2);
            } finally {
                flagAfter.set(Thread.currentThread().isInterrupted());
            }
        }, "flaky4-sleep-interrupt-worker");
        worker.start();

        Thread.sleep(500L);
        worker.interrupt();
        worker.join(15_000L);
        assertTrue(!worker.isAlive(), "worker 应在中断后及时退出，不应挂死");

        Throwable cause = captured.get();
        assertInstanceOf(FfmpegService.FfmpegInterruptedException.class, cause,
                "sleep 被中断应抛专用 FfmpegInterruptedException，实际: " + cause);
        assertInstanceOf(InterruptedException.class, cause.getCause(),
                "cause 必须是 InterruptedException（修复原构造器 cause=null 丢失问题），实际: "
                        + (cause == null ? null : cause.getCause()));
        assertTrue(Boolean.TRUE.equals(flagAfter.get()),
                "withFfmpegRetry 的 catch(InterruptedException) 必须恢复中断标志");
    }
}
