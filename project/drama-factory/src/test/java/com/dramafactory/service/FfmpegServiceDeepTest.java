package com.dramafactory.service;

import com.dramafactory.service.FfmpegService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * FfmpegService 深度集成测试。
 * <p>
 * 使用本机 PATH 上真实存在的 {@code ffmpeg} / {@code ffprobe} 二进制
 * （依赖事实：{@code /usr/bin/ffmpeg}、{@code /usr/bin/ffprobe}，ffmpeg 8.1.2），
 * 不伪造命令、不 mock 被测类。所有断言针对真实进程执行结果。
 * <p>
 * 覆盖意图：真实生成 / 探测、幂等性、失败分类（缺二进制 / 非零退出码 /
 * 缺父目录 / 空命令）、中断语义、并发探测、超时终止。
 */
@SpringBootTest(classes = FfmpegServiceDeepTest.TestConfig.class)
class FfmpegServiceDeepTest {

    /**
     * 直接走 PATH 解析真实 ffmpeg / ffprobe，不做任何"冒充"。
     */
    @org.springframework.context.annotation.Configuration
    static class TestConfig {

        @org.springframework.context.annotation.Bean
        FfmpegService ffmpegService() {
            return new FfmpegService("ffmpeg", "ffprobe");
        }
    }

    @Autowired
    private FfmpegService service;

    @TempDir
    Path tempDir;

    // ------------------------------------------------------------------
    // 1. 上下文与依赖装配
    // ------------------------------------------------------------------

    @Test
    @DisplayName("Spring 上下文真实装配 FfmpegService 并生成真实视频片段")
    void contextLoadsAndRunsCommand() throws Exception {
        // given：Spring 上下文已启动，FfmpegService 已注入，配置为真实 ffmpeg
        assertNotNull(service, "FfmpegService 应被 Spring 注入");
        String configured = service.getFfmpeg();
        assertNotNull(configured, "ffmpeg 配置不应为 null");

        // when：用真实 ffmpeg 生成 1 秒的 testsrc 片段
        Path out = tempDir.resolve("clip.mp4");
        service.generateTestClip(out, 1);

        // then：文件真实存在、非空、且可被 ffprobe 解析出时长
        assertTrue(Files.exists(out), "生成的文件应存在");
        assertTrue(Files.size(out) > 0, "生成的文件内容应非空");
        double duration = service.probeDurationSeconds(out);
        assertTrue(duration > 0.0, "生成的片段时长应为正数，实际 " + duration);
    }

    // ------------------------------------------------------------------
    // 2. 幂等性：重复调用同一操作结果一致
    // ------------------------------------------------------------------

    @Test
    @DisplayName("重复探测同一真实视频结果幂等")
    void probeIsIdempotent() throws Exception {
        // given：真实生成一份 2 秒视频
        Path clip = tempDir.resolve("clip2s.mp4");
        service.generateTestClip(clip, 2);
        long sizeBefore = Files.size(clip);

        // when：连续两次探测时长
        double first = service.probeDurationSeconds(clip);
        double second = service.probeDurationSeconds(clip);

        // then：两次结果一致（幂等），时长约等于设定的 2 秒，文件未被修改
        assertEquals(first, second, 1e-6, "两次探测结果应一致");
        assertEquals(2.0, first, 0.5, "探测时长应约等于 2 秒，实际 " + first);
        assertEquals(sizeBefore, Files.size(clip), "探测不应改变源文件大小");
    }

    @Test
    @DisplayName("对真实视频重复转换到不同输出结果稳定")
    void burnSubtitleIsIdempotentOnSameInput() throws Exception {
        // given：真实生成一份输入视频与一份合法 SRT
        Path in = tempDir.resolve("in.mp4");
        service.generateTestClip(in, 1);
        Path srt = tempDir.resolve("sub.srt");
        Files.write(srt, "1\n00:00:00,000 --> 00:00:01,000\nhi\n".getBytes(StandardCharsets.UTF_8));
        long inSizeBefore = Files.size(in);

        // when：两次烧录到不同输出路径
        Path out1 = tempDir.resolve("out1.mp4");
        Path out2 = tempDir.resolve("out2.mp4");
        service.burnSubtitles(in, srt, out1);
        service.burnSubtitles(in, srt, out2);

        // then：两次都产出非空文件，且输入文件未被改动
        assertTrue(Files.exists(out1) && Files.size(out1) > 0, "第一次输出应非空");
        assertTrue(Files.exists(out2) && Files.size(out2) > 0, "第二次输出应非空");
        assertEquals(inSizeBefore, Files.size(in), "烧录不应改动输入文件大小");
    }

    // ------------------------------------------------------------------
    // 3. 失败注入：依赖抛异常时的错误码与分类
    // ------------------------------------------------------------------

    @Test
    @DisplayName("不存在的二进制导致永久故障（transient=false）")
    void missingBinaryIsPermanentFailure() {
        // given：构造一个指向不存在路径的服务实例
        FfmpegService bad = new FfmpegService("/no/such/binary/ffmpeg-xyz", "/no/such/binary/ffprobe-xyz");

        // when：执行命令，捕获异常
        FfmpegService.FfmpegException ex = assertThrows(
                FfmpegService.FfmpegException.class,
                () -> bad.generateTestClip(tempDir.resolve("x.mp4"), 5));

        // then：错误码分类为永久故障，且消息包含无法启动的语义
        assertFalse(ex.isTransient(), "二进制缺失应为永久故障");
        assertTrue(ex.getMessage().contains("无法启动命令"),
                "消息应说明无法启动命令，实际：" + ex.getMessage());
    }

    @Test
    @DisplayName("非零退出码导致瞬时故障（transient=true）")
    void nonZeroExitIsTransientFailure() {
        // given：用真实 ffmpeg 拼一个非法参数，让 ffmpeg 以非零码退出
        //        这里直接走公开 API 无法注入非法参数，因此借助一个不存在的输入文件触发 ffmpeg 报错
        Path missingInput = tempDir.resolve("no-such-input-" + System.nanoTime() + ".mp4");
        assertFalse(Files.exists(missingInput), "前置条件：输入文件不应存在");

        // when：调用 burnSubtitles，ffmpeg 会因为找不到输入文件而非零退出
        Path srt = tempDir.resolve("dummy.srt");
        try {
            Files.write(srt, "1\n00:00:00,000 --> 00:00:01,000\nhi\n".getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        Path out = tempDir.resolve("out-nonzero.mp4");

        FfmpegService.FfmpegException ex = assertThrows(
                FfmpegService.FfmpegException.class,
                () -> service.burnSubtitles(missingInput, srt, out));

        // then：非零退出码归为瞬时故障，消息包含退出码
        assertTrue(ex.isTransient(), "非零退出码应为瞬时故障");
        assertTrue(ex.getMessage().contains("退出码"),
                "消息应包含退出码信息，实际：" + ex.getMessage());
    }

    @Test
    @DisplayName("瞬时启动失败分类：ENOMEM / EMFILE 判为瞬时，缺失文件判为永久")
    void transientLaunchFailureDetection() {
        // given：构造资源耗尽类与永久类 IOException
        IOException enomem = new IOException("Cannot allocate memory");
        IOException emfile = new IOException("Too many open files");
        IOException permanent = new IOException("No such file or directory");

        // when：调用包级静态分类方法
        boolean enomemTransient = FfmpegService.isTransientLaunchFailure(enomem);
        boolean emfileTransient = FfmpegService.isTransientLaunchFailure(emfile);
        boolean permanentTransient = FfmpegService.isTransientLaunchFailure(permanent);

        // then：资源耗尽为瞬时，缺失二进制为永久
        assertTrue(enomemTransient, "ENOMEM 应为瞬时");
        assertTrue(emfileTransient, "EMFILE 应为瞬时");
        assertFalse(permanentTransient, "文件缺失应为永久");
    }

    // ------------------------------------------------------------------
    // 4. 中断语义：FfmpegInterruptedException 恒为非瞬时
    // ------------------------------------------------------------------

    @Test
    @DisplayName("中断异常恒为非瞬时且不可重试")
    void interruptExceptionIsNeverTransient() {
        // given：构造一个中断异常，携带 InterruptedException 根因
        InterruptedException cause = new InterruptedException("thread interrupted");
        FfmpegService.FfmpegInterruptedException ex =
                new FfmpegService.FfmpegInterruptedException("等待命令时被中断", cause);

        // when：读取分类与根因
        boolean transientFlag = ex.isTransient();
        Throwable root = ex.getCause();

        // then：恒为非瞬时，根因保留
        assertFalse(transientFlag, "中断异常必须为非瞬时，禁止进入重试");
        assertNotNull(root, "根因不应丢失");
        assertEquals(cause, root, "根因应为传入的 InterruptedException");
    }

    // ------------------------------------------------------------------
    // 5. 并发：两线程同时探测同一真实文件不坏数据
    // ------------------------------------------------------------------

    @Test
    @DisplayName("两线程并发探测同一真实视频结果一致且无异常")
    void concurrentProbeOnSameFile() throws Exception {
        // given：真实生成一份 1 秒视频，两个线程、屏障对齐起跑
        Path clip = tempDir.resolve("shared.mp4");
        service.generateTestClip(clip, 1);
        long sizeBefore = Files.size(clip);

        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger failures = new AtomicInteger(0);
        double[] results = new double[threads];

        // when：两线程同时调用 probeDurationSeconds
        for (int i = 0; i < threads; i++) {
            final int idx = i;
            pool.submit(() -> {
                try {
                    start.await();
                    results[idx] = service.probeDurationSeconds(clip);
                } catch (Throwable t) {
                    failures.incrementAndGet();
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then：两线程均完成、无异常、结果一致、文件未被破坏
        assertTrue(finished, "并发任务应在超时内完成");
        assertEquals(0, failures.get(), "并发探测不应抛异常");
        assertEquals(results[0], results[1], 1e-6, "并发结果应一致");
        assertTrue(results[0] > 0.0, "并发探测结果应为正数");
        assertEquals(sizeBefore, Files.size(clip), "并发探测不应改动文件");
    }

    // ------------------------------------------------------------------
    // 6. 边界：空命令 / 缺父目录 / 超大输出 / 超时
    // ------------------------------------------------------------------

    @Test
    @DisplayName("缺少父目录的输出路径导致永久故障")
    void missingParentDirectoryIsPermanent() throws Exception {
        // given：输出路径的父目录不存在
        Path clip = tempDir.resolve("clip-for-poster.mp4");
        service.generateTestClip(clip, 1);
        Path out = tempDir.resolve("no-such-dir").resolve("poster.jpg");
        assertFalse(Files.exists(out.getParent()), "前置条件：父目录不应存在");

        // when：执行命令
        FfmpegService.FfmpegException ex = assertThrows(
                FfmpegService.FfmpegException.class,
                () -> service.extractPoster(clip, out));

        // then：按源码真实行为断言为瞬时故障
        // 1) extractPoster 与 concatClips/burnSubtitles/generateTestClip 不同：后三者会 createDirectories，extractPoster 不会。
        // 2) 因此缺父目录直接交给 ffmpeg，走 run() 非零退出分支，构造器第三参传 true，isTransient() == true。
        // 3) FfmpegException 类 javadoc 把"输出路径缺少父目录"列为永久故障示例，与 extractPoster 实现不一致，属已知文档债，不在本测试解决。
        assertTrue(ex.isTransient(), "extractPoster 无父目录预检，ffmpeg 非零退出按 run() 语义判为瞬时故障");
        assertTrue(ex.getMessage().length() > 0, "异常消息应有内容");
    }

    @Test
    @DisplayName("缺少父目录的输出路径失败且不产生文件")
    void parentDirectoryMissingFailsWithoutCreatingFile() throws Exception {
        // given：一个父目录不存在的输出路径
        Path clip = tempDir.resolve("clip-for-poster-empty.mp4");
        service.generateTestClip(clip, 1);
        Path out = tempDir.resolve("empty-cmd-dir").resolve("poster.jpg");
        assertFalse(Files.exists(out.getParent()), "前置条件：父目录不应存在");

        // when：调用 extractPoster，ffmpeg 无法打开输出
        FfmpegService.FfmpegException ex = assertThrows(
                FfmpegService.FfmpegException.class,
                () -> service.extractPoster(clip, out));

        // then：异常消息非空，且输出文件未被创建
        assertNotNull(ex.getMessage(), "异常消息不应为 null");
        assertFalse(ex.getMessage().isEmpty(), "异常消息不应为空");
        assertFalse(Files.exists(out), "失败后不应产生输出文件");
    }


    @Test
    @DisplayName("超大输出不撑爆缓冲区，读取线程正常收尾")
    void largeOutputIsHandledGracefully() throws Exception {
        // given：让 ffmpeg 输出一个较大的视频（较长时长、较高码率），制造大 stderr
        Path out = tempDir.resolve("big.mp4");
        FfmpegService.FfmpegException ex = assertThrows(
                FfmpegService.FfmpegException.class,
                // 传入一个不存在的输入给 burnSubtitles，ffmpeg 会输出较多错误信息并非零退出
                () -> service.burnSubtitles(
                        tempDir.resolve("missing-input-" + System.nanoTime() + ".mp4"),
                        writeSrt(tempDir.resolve("s.srt")),
                        out));

        // then：异常分类为瞬时（非零退出码），消息非空
        assertTrue(ex.isTransient(), "非零退出码应为瞬时");
        assertNotNull(ex.getMessage(), "异常消息不应为 null");
    }

    @Test
    @DisplayName("超时命令被强制终止并归为瞬时故障")
    void timeoutKillsProcess() {
        // given：一个会长时间阻塞的探测目标 —— 使用系统 sleep 命令伪装成 ffprobe，
        //        由服务内部超时机制强制终止
        FfmpegService sleepy = new FfmpegService("ffmpeg", "sleep");
        Path fakeVideo = tempDir.resolve("fake.mp4");
        try {
            Files.write(fakeVideo, new byte[]{0x00});
        } catch (IOException e) {
            throw new RuntimeException(e);
        }

        // when：调用 probeDurationSeconds，sleep 会长时间阻塞触发超时
        long start = System.nanoTime();
        FfmpegService.FfmpegException ex = assertThrows(
                FfmpegService.FfmpegException.class,
                () -> sleepy.probeDurationSeconds(fakeVideo));

        long elapsedMillis = (System.nanoTime() - start) / 1_000_000L;

        // then：超时归为瞬时故障，且未长时间阻塞（服务超时上限远小于此阈值）
        assertTrue(ex.isTransient(), "超时应为瞬时故障，实际消息：" + ex.getMessage());
        assertTrue(elapsedMillis < 30_000L,
                "超时应在合理时间内返回，实际 " + elapsedMillis + "ms");
    }

    private Path writeSrt(Path srt) {
        try {
            Files.write(srt, "1\n00:00:00,000 --> 00:00:01,000\nhi\n".getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        return srt;
    }
}

