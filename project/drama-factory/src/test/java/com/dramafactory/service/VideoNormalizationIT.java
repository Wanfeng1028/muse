package com.dramafactory.service;

import com.dramafactory.service.VideoNormalizationService.FitMode;
import com.dramafactory.service.VideoNormalizationService.SegmentReport;
import com.dramafactory.service.VideoNormalizationService.SegmentStatus;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * VideoNormalizationService 真实 ffmpeg 集成测试：缺二进制自动跳过。
 */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class VideoNormalizationIT {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeAll
    void checkFfmpegAvailable() {
        Assumptions.assumeTrue(canRun("ffmpeg", "-version"), "缺 ffmpeg，跳过");
        Assumptions.assumeTrue(canRun("ffprobe", "-version"), "缺 ffprobe，跳过");
    }

    private static boolean canRun(String... cmd) {
        try {
            Process p = new ProcessBuilder(cmd).redirectErrorStream(true).start();
            p.getInputStream().readAllBytes();
            return p.waitFor() == 0;
        } catch (Exception e) {
            return false;
        }
    }

    @Test
    void normalizeAll_realFfmpeg(@TempDir Path dir) throws Exception {
        FfmpegService ffmpegService = new FfmpegService("ffmpeg", "ffprobe");
        VideoNormalizationService.CommandRunner runner = ffmpegService::executeCapture;
        SuperResolutionProvider sr = new SuperResolutionProvider() {
            @Override
            public boolean isAvailable() {
                return false;
            }

            @Override
            public Path enhance(Path input, Path workDir) {
                throw new IllegalStateException("NoOp");
            }
        };
        VideoNormalizationService service = new VideoNormalizationService(
                runner, objectMapper, sr, "ffmpeg", "ffprobe", true,
                1280, 720, 30.0, 23, FitMode.PAD, 300, 1);

        Path small = dir.resolve("small.mp4");
        Path big = dir.resolve("big.mp4");

        runner.run(List.of("ffmpeg", "-y", "-f", "lavfi",
                "-i", "testsrc=duration=2:size=640x360:rate=25",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", small.toString()), 300);

        runner.run(List.of("ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=2:size=1280x720:rate=30",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-shortest", big.toString()), 300);

        assertTrue(Files.exists(small), "small.mp4 应生成");
        assertTrue(Files.exists(big), "big.mp4 应生成");

        Path workDir = Files.createDirectories(dir.resolve("work"));
        List<SegmentReport> reports = service.normalizeAll(List.of(small, big), workDir);

        assertEquals(2, reports.size(), "应返回两条报告");
        SegmentReport smallReport = reports.get(0);
        SegmentReport bigReport = reports.get(1);

        assertTrue(smallReport.ok(), "small 应成功");
        assertTrue(smallReport.upsampled(), "small 应被标记放大");
        assertEquals(SegmentStatus.OK_TRANSCODED, smallReport.status(), "small 应被转码");

        assertTrue(bigReport.ok(), "big 应成功");
        assertEquals(SegmentStatus.OK_NATIVE, bigReport.status(), "big 已达标应走拷贝");

        assertNotNull(smallReport.output(), "small 输出路径不应为空");
        String probeJson = runner.run(List.of("ffprobe", "-v", "quiet",
                "-print_format", "json", "-show_streams", "-show_format",
                smallReport.output().toString()), 300);
        JsonNode root = objectMapper.readTree(probeJson);
        JsonNode video = null;
        for (JsonNode s : root.path("streams")) {
            if ("video".equals(s.path("codec_type").asText())) {
                video = s;
                break;
            }
        }
        assertNotNull(video, "输出应含视频流");
        assertEquals(1280, video.path("width").asInt(), "输出宽度应为 1280");
        assertEquals(720, video.path("height").asInt(), "输出高度应为 720");
    }
}
