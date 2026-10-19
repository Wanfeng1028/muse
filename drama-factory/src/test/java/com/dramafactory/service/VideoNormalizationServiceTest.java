package com.dramafactory.service;

import com.dramafactory.service.VideoNormalizationService.CommandRunner;
import com.dramafactory.service.VideoNormalizationService.FitMode;
import com.dramafactory.service.VideoNormalizationService.SegmentReport;
import com.dramafactory.service.VideoNormalizationService.SegmentStatus;
import com.dramafactory.service.VideoNormalizationService.SourceInfo;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * VideoNormalizationService 纯单测：使用 fake CommandRunner，不依赖真实 ffmpeg。
 */
class VideoNormalizationServiceTest {

    /** 1280x720 达标 fixture，带 aac 音频。 */
    private static final String PROBE_HD = "{\"streams\":["
            + "{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":1280,\"height\":720,"
            + "\"avg_frame_rate\":\"30/1\",\"pix_fmt\":\"yuv420p\"},"
            + "{\"codec_type\":\"audio\",\"codec_name\":\"aac\",\"sample_rate\":\"44100\"}"
            + "],\"format\":{\"duration\":\"5.0\"}}";

    /** 640x360 小分辨率 fixture，无音频。 */
    private static final String PROBE_SMALL = "{\"streams\":["
            + "{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":640,\"height\":360,"
            + "\"avg_frame_rate\":\"25/1\",\"pix_fmt\":\"yuv420p\"}"
            + "],\"format\":{\"duration\":\"4.0\"}}";

    /** 达标视频但音频为 mp3。 */
    private static final String PROBE_MP3_AUDIO = "{\"streams\":["
            + "{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":1280,\"height\":720,"
            + "\"avg_frame_rate\":\"30/1\",\"pix_fmt\":\"yuv420p\"},"
            + "{\"codec_type\":\"audio\",\"codec_name\":\"mp3\",\"sample_rate\":\"44100\"}"
            + "],\"format\":{\"duration\":\"5.0\"}}";

    /**
     * fake CommandRunner：按文件名返回 probe JSON；ffmpeg 命令则创建输出文件。
     * 记录所有 command 供断言。
     */
    static final class FakeCommandRunner implements CommandRunner {
        final Map<String, String> probeJsonByFileName;
        final List<List<String>> commands = new ArrayList<>();
        final Map<String, AtomicInteger> probeCounts = new HashMap<>();

        FakeCommandRunner(Map<String, String> probeJsonByFileName) {
            this.probeJsonByFileName = probeJsonByFileName;
        }

        @Override
        public String run(List<String> command, long timeoutSeconds) {
            commands.add(new ArrayList<>(command));
            String first = command.isEmpty() ? "" : command.get(0);
            if (first.contains("ffprobe")) {
                String fileName = fileNameOf(command.get(command.size() - 1));
                int count = probeCounts.computeIfAbsent(fileName, k -> new AtomicInteger()).incrementAndGet();
                String json = probeJsonByFileName.get(fileName);
                if (json == null) {
                    throw new FfmpegService.FfmpegException("no fixture for " + fileName, false);
                }
                // 支持通过 "fileName#2" 形式为 verify 阶段的第二次 probe 指定不同 JSON
                String secondKey = fileName + "#" + count;
                if (probeJsonByFileName.containsKey(secondKey)) {
                    return probeJsonByFileName.get(secondKey);
                }
                return json;
            }
            if (first.contains("ffmpeg")) {
                Path out = Path.of(command.get(command.size() - 1));
                try {
                    if (out.getParent() != null) {
                        Files.createDirectories(out.getParent());
                    }
                    Files.createFile(out);
                } catch (IOException e) {
                    throw new FfmpegService.FfmpegException("cannot create output", e, false);
                }
                return "";
            }
            return "";
        }

        private static String fileNameOf(String path) {
            Path p = Path.of(path);
            return p.getFileName() == null ? path : p.getFileName().toString();
        }

        boolean hasFfmpegCommand() {
            for (List<String> c : commands) {
                if (!c.isEmpty() && c.get(0).contains("ffmpeg") && !c.get(0).contains("ffprobe")) {
                    return true;
                }
            }
            return false;
        }

        List<String> firstFfmpegCommand() {
            for (List<String> c : commands) {
                if (!c.isEmpty() && c.get(0).contains("ffmpeg") && !c.get(0).contains("ffprobe")) {
                    return c;
                }
            }
            return null;
        }
    }

    /** 不做任何事的超分实现。 */
    static final class NoOpSuperResolutionProvider implements SuperResolutionProvider {
        @Override
        public boolean isAvailable() {
            return false;
        }

        @Override
        public Path enhance(Path input, Path workDir) {
            throw new IllegalStateException("should not be called");
        }
    }

    private VideoNormalizationService newService(CommandRunner runner, SuperResolutionProvider sr) {
        return new VideoNormalizationService(runner, new ObjectMapper(), sr,
                "ffmpeg", "ffprobe", true, 1280, 720, 30.0, 20, FitMode.PAD, 600, 2);
    }

    private VideoNormalizationService newService(CommandRunner runner, SuperResolutionProvider sr, FitMode fitMode) {
        return new VideoNormalizationService(runner, new ObjectMapper(), sr,
                "ffmpeg", "ffprobe", true, 1280, 720, 30.0, 20, fitMode, 600, 2);
    }

    private static Path writeInput(Path dir, String name, String content) throws IOException {
        Path p = dir.resolve(name);
        Files.writeString(p, content);
        return p;
    }

    @Test
    void nativeClip_isCopiedWithoutTranscode(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "native.mp4", "NATIVE-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("native.mp4", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("native.mp4");
        SegmentReport report = service.normalize(input, output);

        assertEquals(SegmentStatus.OK_NATIVE, report.status(), "达标片段应标记 OK_NATIVE");
        assertFalse(report.upsampled(), "达标片段不应被放大");
        assertTrue(report.ok(), "达标片段应 ok()");
        assertFalse(runner.hasFfmpegCommand(), "不应触发任何 ffmpeg 转码命令");
        assertTrue(Files.exists(output), "输出文件应存在");
        assertEquals("NATIVE-BYTES", Files.readString(output), "输出应与输入字节相同");
    }

    @Test
    void smallClip_isUpscaledAndFlagged(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        fixtures.put("small.mp4#2", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("small.mp4");
        SegmentReport report = service.normalize(input, output);

        assertEquals(SegmentStatus.OK_TRANSCODED, report.status(), "小片段应被转码");
        assertTrue(report.upsampled(), "小片段应被标记放大");
        assertTrue(report.ok(), "转码成功应 ok()");

        List<String> ffmpegCmd = runner.firstFfmpegCommand();
        assertNotNull(ffmpegCmd, "应存在 ffmpeg 转码命令");
        String joined = String.join(" ", ffmpegCmd);
        assertTrue(joined.contains(
                        "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black"),
                "PAD 模式应包含 scale+pad 滤镜，实际: " + joined);
    }

    @Test
    void cropMode_usesCropFilter(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        fixtures.put("small.mp4#2", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service =
                newService(runner, new NoOpSuperResolutionProvider(), FitMode.CROP);

        Path output = dir.resolve("out").resolve("small.mp4");
        service.normalize(input, output);

        List<String> ffmpegCmd = runner.firstFfmpegCommand();
        assertNotNull(ffmpegCmd, "应存在 ffmpeg 转码命令");
        String joined = String.join(" ", ffmpegCmd);
        assertTrue(joined.contains("crop=1280:720"), "CROP 模式应包含 crop 滤镜，实际: " + joined);
        assertTrue(joined.contains("force_original_aspect_ratio=increase"),
                "CROP 模式应使用 increase，实际: " + joined);
    }

    @Test
    void superResolution_usedWhenAvailable(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        fixtures.put("small.mp4#2", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);

        Path workDir = Files.createDirectories(dir.resolve("work"));
        Path enhanced = workDir.resolve("enhanced.mp4");
        AtomicInteger enhanceCalls = new AtomicInteger();
        SuperResolutionProvider sr = new SuperResolutionProvider() {
            @Override
            public boolean isAvailable() {
                return true;
            }

            @Override
            public Path enhance(Path in, Path wd) {
                enhanceCalls.incrementAndGet();
                try {
                    Files.createFile(enhanced);
                } catch (IOException e) {
                    throw new RuntimeException(e);
                }
                return enhanced;
            }
        };
        VideoNormalizationService service = newService(runner, sr);

        Path output = dir.resolve("out").resolve("small.mp4");
        service.normalize(input, output);

        assertEquals(1, enhanceCalls.get(), "可用时应调用一次 enhance");
        List<String> ffmpegCmd = runner.firstFfmpegCommand();
        assertNotNull(ffmpegCmd, "应存在 ffmpeg 转码命令");
        int iIdx = ffmpegCmd.indexOf("-i");
        assertTrue(iIdx >= 0, "ffmpeg 命令应含 -i");
        assertTrue(ffmpegCmd.get(iIdx + 1).endsWith("enhanced.mp4"),
                "转码输入应为 enhanced.mp4，实际: " + ffmpegCmd.get(iIdx + 1));
    }

    @Test
    void superResolutionDowngrade_whenUnavailable(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        fixtures.put("small.mp4#2", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);

        AtomicInteger enhanceCalls = new AtomicInteger();
        SuperResolutionProvider sr = new SuperResolutionProvider() {
            @Override
            public boolean isAvailable() {
                return false;
            }

            @Override
            public Path enhance(Path in, Path wd) {
                enhanceCalls.incrementAndGet();
                return in;
            }
        };
        VideoNormalizationService service = newService(runner, sr);

        Path output = dir.resolve("out").resolve("small.mp4");
        SegmentReport report = service.normalize(input, output);

        assertEquals(0, enhanceCalls.get(), "不可用时不调用 enhance");
        assertEquals(SegmentStatus.OK_TRANSCODED, report.status(), "仍应走普通转码");
        List<String> ffmpegCmd = runner.firstFfmpegCommand();
        assertNotNull(ffmpegCmd, "应存在普通 scale 转码命令");
        String joined = String.join(" ", ffmpegCmd);
        assertTrue(joined.contains("scale=1280:720"), "应包含普通 scale，实际: " + joined);
    }

    @Test
    void singleFailure_doesNotPoisonBatch(@TempDir Path dir) throws IOException {
        Path a = writeInput(dir, "a.mp4", "A");
        Path b = writeInput(dir, "b.mp4", "B");
        Path c = writeInput(dir, "c.mp4", "C");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("a.mp4", PROBE_HD);
        fixtures.put("c.mp4", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path workDir = Files.createDirectories(dir.resolve("work"));
        List<SegmentReport> reports = service.normalizeAll(List.of(a, b, c), workDir);

        assertEquals(3, reports.size(), "应返回三条报告");
        assertTrue(reports.get(0).ok(), "第 1 条应成功");
        assertEquals(SegmentStatus.FAILED, reports.get(1).status(), "第 2 条应失败");
        assertNotNull(reports.get(1).errorMessage(), "失败报告应含错误信息");
        assertFalse(reports.get(1).errorMessage().isBlank(), "错误信息不应为空");
        assertTrue(reports.get(2).ok(), "第 3 条应成功");
    }

    @Test
    void nullInput_throwsIllegalArgumentException() {
        FakeCommandRunner runner = new FakeCommandRunner(new HashMap<>());
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());
        assertThrows(IllegalArgumentException.class,
                () -> service.normalize(null, Path.of("out.mp4")),
                "null 输入应抛 IllegalArgumentException");
    }

    @Test
    void verifyRejectsWrongResolution(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        // verify 阶段的第二次 probe 仍返回小分辨率 → 与目标不符
        fixtures.put("small.mp4#2", PROBE_SMALL);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("small.mp4");
        assertThrows(FfmpegService.FfmpegException.class,
                () -> service.normalize(input, output),
                "转码后 verify 分辨率不符应抛 FfmpegException");
    }

    @Test
    void audioNonAac_triggersTranscode(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "mp3.mp4", "MP3-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("mp3.mp4", PROBE_MP3_AUDIO);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("mp3.mp4");
        SegmentReport report = service.normalize(input, output);

        assertEquals(SegmentStatus.OK_TRANSCODED, report.status(), "音频非 aac 应触发转码");
        assertFalse(report.upsampled(), "视频分辨率达标，不应标记放大");
        assertTrue(runner.hasFfmpegCommand(), "应执行 ffmpeg 转码命令");
    }
}
