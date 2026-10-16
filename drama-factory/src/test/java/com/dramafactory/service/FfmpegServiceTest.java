package com.dramafactory.service;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * FfmpegService 的流水线单元测试。
 * 不启动 Spring，直接 new 出被测服务，依赖本机可用的 ffmpeg / ffprobe。
 */
class FfmpegServiceTest {

    /** 相对工作目录，避免使用 /tmp 造成跨平台问题。 */
    private static final Path WORK_DIR = Path.of("target", "test-ffmpeg");

    private FfmpegService ffmpegService;

    @BeforeEach
    void setUp() throws IOException {
        // 构造器参数为 ffmpeg / ffprobe 可执行文件名
        ffmpegService = new FfmpegService("ffmpeg", "ffprobe");
        // 每次都创建干净的测试工作目录
        if (Files.exists(WORK_DIR)) {
            deleteRecursively(WORK_DIR);
        }
        Files.createDirectories(WORK_DIR);
    }

    @AfterEach
    void tearDown() throws IOException {
        // 可选清理：删除测试产物，保持工作区整洁
        if (Files.exists(WORK_DIR)) {
            deleteRecursively(WORK_DIR);
        }
    }

    /**
     * 验证「生成片段 -> 拼接 -> 探测时长」整条流水线。
     * 3 个 2 秒片段拼接后总时长应约为 6 秒。
     */
    @Test
    @Timeout(value = 120, unit = TimeUnit.SECONDS)
    void generateAndConcat() throws IOException {
        // 生成 3 个 2 秒测试片段
        Path clip1 = WORK_DIR.resolve("clip1.mp4");
        Path clip2 = WORK_DIR.resolve("clip2.mp4");
        Path clip3 = WORK_DIR.resolve("clip3.mp4");

        ffmpegService.generateTestClip(clip1, 2);
        ffmpegService.generateTestClip(clip2, 2);
        ffmpegService.generateTestClip(clip3, 2);

        assertTrue(Files.exists(clip1), "clip1.mp4 应已生成");
        assertTrue(Files.exists(clip2), "clip2.mp4 应已生成");
        assertTrue(Files.exists(clip3), "clip3.mp4 应已生成");

        // 合并为 joined.mp4
        Path joined = WORK_DIR.resolve("joined.mp4");
        ffmpegService.concatClips(List.of(clip1, clip2, clip3), joined);

        assertTrue(Files.exists(joined), "joined.mp4 应已生成");
        assertTrue(Files.size(joined) > 0, "joined.mp4 大小应大于 0");

        // 断言合并后时长在 5.5 ~ 6.5 秒之间
        double duration = ffmpegService.probeDurationSeconds(joined);
        assertTrue(duration >= 5.5 && duration <= 6.5,
                "合并后时长应约为 6 秒，实际为 " + duration + " 秒");
    }

    /**
     * 验证「烧录字幕 -> 输出文件存在 -> 时长基本不变」。
     */
    @Test
    @Timeout(value = 120, unit = TimeUnit.SECONDS)
    void burnSubtitles() throws IOException {
        // 先生成一个 2 秒片段，再复制拼接成与原片对应的输入
        Path clip1 = WORK_DIR.resolve("clip1.mp4");
        Path clip2 = WORK_DIR.resolve("clip2.mp4");
        ffmpegService.generateTestClip(clip1, 2);
        ffmpegService.generateTestClip(clip2, 2);

        Path joined = WORK_DIR.resolve("joined.mp4");
        ffmpegService.concatClips(List.of(clip1, clip2), joined);
        double originalDuration = ffmpegService.probeDurationSeconds(joined);

        // 手写一个简单 SRT，含两句中文
        Path srt = WORK_DIR.resolve("subtitle.srt");
        String srtContent = """
                1
                00:00:00,000 --> 00:00:01,500
                这是第一句中文字幕

                2
                00:00:01,500 --> 00:00:03,000
                这是第二句中文字幕

                """;
        Files.writeString(srt, srtContent, StandardCharsets.UTF_8);
        assertTrue(Files.size(srt) > 0, "SRT 字幕文件应已写入内容");

        // 烧录字幕
        Path subtitled = WORK_DIR.resolve("subtitled.mp4");
        ffmpegService.burnSubtitles(joined, srt, subtitled);

        assertTrue(Files.exists(subtitled), "subtitled.mp4 应已生成");
        assertTrue(Files.size(subtitled) > 0, "subtitled.mp4 大小应大于 0");

        // 烧录字幕后时长应与原片基本一致（差值 < 1 秒）
        double subtitledDuration = ffmpegService.probeDurationSeconds(subtitled);
        double diff = Math.abs(subtitledDuration - originalDuration);
        assertTrue(diff < 1.0,
                "烧录字幕后时长差值应小于 1 秒，原时长=" + originalDuration
                        + "，新时长=" + subtitledDuration + "，差值=" + diff);
    }

    @Test
    @Timeout(value = 120, unit = TimeUnit.SECONDS)
    void probeDurationSeconds_measuresRealDuration() {
        Path clip = WORK_DIR.resolve("probe_me.mp4");
        ffmpegService.generateTestClip(clip, 3);
        double duration = ffmpegService.probeDurationSeconds(clip);
        assertTrue(duration >= 2.5 && duration <= 3.5,
                "3s clip probed duration should be 2.5~3.5s, actual " + duration);
    }

    @Test
    @Timeout(value = 120, unit = TimeUnit.SECONDS)
    void extractPoster_producesJpeg() throws IOException {
        Path clip = WORK_DIR.resolve("poster_src.mp4");
        ffmpegService.generateTestClip(clip, 2);
        Path poster = WORK_DIR.resolve("poster.jpg");
        ffmpegService.extractPoster(clip, poster);
        assertTrue(Files.exists(poster), "poster frame should exist");
        assertTrue(Files.size(poster) > 0, "poster frame size should be > 0");
    }

    /**
     * 递归删除目录及其内容，用于清理测试产物。
     */
    private static void deleteRecursively(Path root) throws IOException {
        assertNotNull(root, "待删除目录不能为 null");
        if (!Files.exists(root)) {
            return;
        }
        try (var stream = Files.walk(root)) {
            stream.sorted((a, b) -> b.getNameCount() - a.getNameCount())
                    .forEach(p -> {
                        try {
                            Files.deleteIfExists(p);
                        } catch (IOException e) {
                            throw new RuntimeException("删除失败: " + p, e);
                        }
                    });
        }
    }
}
