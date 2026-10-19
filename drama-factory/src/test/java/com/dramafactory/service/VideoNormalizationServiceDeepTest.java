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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * VideoNormalizationService 深度单测：纯单元测试，使用包可见测试构造器 + fake CommandRunner，
 * 不起 Spring 上下文，不依赖真实 ffmpeg/ffprobe。
 *
 * <p>唯一被 fake 的是外部不可达的进程调用（ffmpeg/ffprobe 命令行执行），
 * 通过注入 {@link CommandRunner} 实现，被测逻辑本身走真实实现。</p>
 */
class VideoNormalizationServiceDeepTest {

    private static final String PROBE_HD = "{\"streams\":["
            + "{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":1280,\"height\":720,"
            + "\"avg_frame_rate\":\"30/1\",\"pix_fmt\":\"yuv420p\"},"
            + "{\"codec_type\":\"audio\",\"codec_name\":\"aac\",\"sample_rate\":\"44100\"}"
            + "],\"format\":{\"duration\":\"5.0\"}}";

    private static final String PROBE_SMALL = "{\"streams\":["
            + "{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":640,\"height\":360,"
            + "\"avg_frame_rate\":\"25/1\",\"pix_fmt\":\"yuv420p\"}"
            + "],\"format\":{\"duration\":\"4.0\"}}";

    private static final String PROBE_NO_VIDEO = "{\"streams\":["
            + "{\"codec_type\":\"audio\",\"codec_name\":\"aac\",\"sample_rate\":\"44100\"}"
            + "],\"format\":{\"duration\":\"4.0\"}}";

    private static final String PROBE_EMPTY_FPS = "{\"streams\":["
            + "{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":1280,\"height\":720,"
            + "\"avg_frame_rate\":\"\",\"pix_fmt\":\"yuv420p\"}"
            + "],\"format\":{\"duration\":\"4.0\"}}";

    private static final String PROBE_FPS_DECIMAL = "{\"streams\":["
            + "{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":1280,\"height\":720,"
            + "\"avg_frame_rate\":\"29.97\",\"pix_fmt\":\"yuv420p\"}"
            + "],\"format\":{\"duration\":\"4.0\"}}";

    private static final String PROBE_FPS_FRACTION_NEAR = "{\"streams\":["
            + "{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":1280,\"height\":720,"
            + "\"avg_frame_rate\":\"3000/100\",\"pix_fmt\":\"yuv420p\"}"
            + "],\"format\":{\"duration\":\"4.0\"}}";

    /** fake CommandRunner：按文件名返回 probe JSON；ffmpeg 命令则创建输出文件。 */
    static final class FakeCommandRunner implements CommandRunner {
        final Map<String, String> probeJsonByFileName;
        final List<List<String>> commands = new ArrayList<>();
        final Map<String, AtomicInteger> probeCounts = new HashMap<>();
        volatile CommandRunner override;

        FakeCommandRunner(Map<String, String> probeJsonByFileName) {
            this.probeJsonByFileName = probeJsonByFileName;
        }

        @Override
        public String run(List<String> command, long timeoutSeconds) {
            if (override != null) {
                return override.run(command, timeoutSeconds);
            }
            commands.add(new ArrayList<>(command));
            String first = command.isEmpty() ? "" : command.get(0);
            if (first.contains("ffprobe")) {
                String fileName = fileNameOf(command.get(command.size() - 1));
                int count = probeCounts.computeIfAbsent(fileName, k -> new AtomicInteger()).incrementAndGet();
                String json = probeJsonByFileName.get(fileName);
                if (json == null) {
                    throw new FfmpegService.FfmpegException("no fixture for " + fileName, false);
                }
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
    }

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

    private static Path writeInput(Path dir, String name, String content) throws IOException {
        Path p = dir.resolve(name);
        Files.writeString(p, content);
        return p;
    }

    // ---------- 构造器参数校验 ----------

    @Test
    void constructor_rejectsOddWidth() {
        assertThatThrownBy(() -> new VideoNormalizationService(
                (cmd, t) -> "", new ObjectMapper(), new NoOpSuperResolutionProvider(),
                "ffmpeg", "ffprobe", true, 1279, 720, 30.0, 20, FitMode.PAD, 600, 2))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("width");
    }

    @Test
    void constructor_rejectsNegativeFps() {
        assertThatThrownBy(() -> new VideoNormalizationService(
                (cmd, t) -> "", new ObjectMapper(), new NoOpSuperResolutionProvider(),
                "ffmpeg", "ffprobe", true, 1280, 720, -1.0, 20, FitMode.PAD, 600, 2))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("fps");
    }

    @Test
    void constructor_rejectsCrfOutOfRange() {
        assertThatThrownBy(() -> new VideoNormalizationService(
                (cmd, t) -> "", new ObjectMapper(), new NoOpSuperResolutionProvider(),
                "ffmpeg", "ffprobe", true, 1280, 720, 30.0, 52, FitMode.PAD, 600, 2))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("crf");

        assertThatThrownBy(() -> new VideoNormalizationService(
                (cmd, t) -> "", new ObjectMapper(), new NoOpSuperResolutionProvider(),
                "ffmpeg", "ffprobe", true, 1280, 720, 30.0, -1, FitMode.PAD, 600, 2))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("crf");
    }

    // ---------- probe 解析 ----------

    @Test
    void probe_parsesFractionAndDecimalFrameRates() {
        FakeCommandRunner runner = new FakeCommandRunner(new HashMap<>());
        runner.probeJsonByFileName.put("frac.mp4", PROBE_FPS_FRACTION_NEAR);
        runner.probeJsonByFileName.put("dec.mp4", PROBE_FPS_DECIMAL);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        SourceInfo frac = service.probe(Path.of("frac.mp4"));
        assertThat(frac.fps()).isEqualTo(30.0);
        assertThat(frac.width()).isEqualTo(1280);
        assertThat(frac.height()).isEqualTo(720);

        SourceInfo dec = service.probe(Path.of("dec.mp4"));
        assertThat(dec.fps()).isEqualTo(29.97);
    }

    @Test
    void probe_returnsNegativeFpsForEmptyValue() {
        FakeCommandRunner runner = new FakeCommandRunner(new HashMap<>());
        runner.probeJsonByFileName.put("emptyfps.mp4", PROBE_EMPTY_FPS);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        SourceInfo info = service.probe(Path.of("emptyfps.mp4"));
        assertThat(info.fps()).isEqualTo(-1.0);
        assertThat(info.width()).isEqualTo(1280);
    }

    @Test
    void probe_throwsWhenNoVideoStream() {
        FakeCommandRunner runner = new FakeCommandRunner(new HashMap<>());
        runner.probeJsonByFileName.put("audioonly.mp4", PROBE_NO_VIDEO);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        assertThatThrownBy(() -> service.probe(Path.of("audioonly.mp4")))
                .isInstanceOf(FfmpegService.FfmpegException.class)
                .hasMessageContaining("视频流");
    }

    // ---------- conforms 边界 ----------

    @Test
    void conforms_fpsWithinToleranceIsAccepted_boundaryRejected() {
        FakeCommandRunner runner = new FakeCommandRunner(new HashMap<>());
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        SourceInfo exactly = new SourceInfo(1280, 720, 30.0, "h264", "yuv420p", true, "aac");
        assertThat(service.conforms(exactly)).isTrue();

        SourceInfo justWithin = new SourceInfo(1280, 720, 30.019, "h264", "yuv420p", false, null);
        assertThat(service.conforms(justWithin)).isTrue();

        SourceInfo atBoundary = new SourceInfo(1280, 720, 30.02, "h264", "yuv420p", false, null);
        assertThat(service.conforms(atBoundary)).isFalse();

        SourceInfo justOutside = new SourceInfo(1280, 720, 30.021, "h264", "yuv420p", false, null);
        assertThat(service.conforms(justOutside)).isFalse();

        SourceInfo zeroFps = new SourceInfo(1280, 720, 0.0, "h264", "yuv420p", false, null);
        assertThat(service.conforms(zeroFps)).isFalse();
    }

    // ---------- normalize 输入校验 ----------

    @Test
    void normalize_throwsWhenInputMissingOrNotRegularFile(@TempDir Path dir) throws IOException {
        FakeCommandRunner runner = new FakeCommandRunner(new HashMap<>());
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path missing = dir.resolve("nope.mp4");
        assertThatThrownBy(() -> service.normalize(missing, dir.resolve("out.mp4")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("不存在");

        Path aDir = Files.createDirectories(dir.resolve("aDir"));
        assertThatThrownBy(() -> service.normalize(aDir, dir.resolve("out.mp4")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("非普通文件");
    }

    // ---------- OK_NATIVE 拷贝路径 ----------

    @Test
    void normalize_nativeCopiesBytesWithoutAnyCommand(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "native.mp4", "NATIVE-BYTES-1234");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("native.mp4", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("native.mp4");
        SegmentReport report = service.normalize(input, output);

        assertThat(report.status()).isEqualTo(SegmentStatus.OK_NATIVE);
        assertThat(report.upsampled()).isFalse();
        assertThat(report.ok()).isTrue();
        assertThat(report.sourceWidth()).isEqualTo(1280);
        assertThat(report.sourceHeight()).isEqualTo(720);
        assertThat(report.errorMessage()).isNull();
        assertThat(runner.hasFfmpegCommand()).isFalse();
        assertThat(Files.readString(output)).isEqualTo("NATIVE-BYTES-1234");
    }

    // ---------- upscale 标记 ----------

    @Test
    void normalize_flagsUpscaleWhenSourceSmaller(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        fixtures.put("small.mp4#2", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("small.mp4");
        SegmentReport report = service.normalize(input, output);

        assertThat(report.status()).isEqualTo(SegmentStatus.OK_TRANSCODED);
        assertThat(report.upsampled()).isTrue();
        assertThat(report.sourceWidth()).isEqualTo(640);
        assertThat(report.sourceHeight()).isEqualTo(360);
        assertThat(runner.hasFfmpegCommand()).isTrue();
    }

    // ---------- 转码重试 ----------

    @Test
    void normalize_retriesTransientThenSucceeds(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        fixtures.put("small.mp4#2", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);

        AtomicInteger ffmpegCalls = new AtomicInteger();
        CommandRunner wrapped = (command, timeoutSeconds) -> {
            String first = command.isEmpty() ? "" : command.get(0);
            if (first.contains("ffmpeg") && !first.contains("ffprobe")) {
                int n = ffmpegCalls.incrementAndGet();
                if (n == 1) {
                    throw new FfmpegService.FfmpegException("transient boom", true);
                }
            }
            return runner.run(command, timeoutSeconds);
        };
        VideoNormalizationService service = newService(wrapped, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("small.mp4");
        SegmentReport report = service.normalize(input, output);

        assertThat(report.status()).isEqualTo(SegmentStatus.OK_TRANSCODED);
        assertThat(ffmpegCalls.get()).isEqualTo(2);
    }

    @Test
    void normalize_doesNotRetryNonTransientFailure(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        fixtures.put("small.mp4#2", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);

        AtomicInteger ffmpegCalls = new AtomicInteger();
        CommandRunner wrapped = (command, timeoutSeconds) -> {
            String first = command.isEmpty() ? "" : command.get(0);
            if (first.contains("ffmpeg") && !first.contains("ffprobe")) {
                ffmpegCalls.incrementAndGet();
                throw new FfmpegService.FfmpegException("fatal boom", false);
            }
            return runner.run(command, timeoutSeconds);
        };
        VideoNormalizationService service = newService(wrapped, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("small.mp4");
        assertThatThrownBy(() -> service.normalize(input, output))
                .isInstanceOf(FfmpegService.FfmpegException.class)
                .hasMessageContaining("fatal boom");
        assertThat(ffmpegCalls.get()).isEqualTo(1);
    }

    // ---------- verify 校验失败 ----------

    @Test
    void normalize_failsWhenVerifyProbeReportsWrongResolution(@TempDir Path dir) throws IOException {
        Path input = writeInput(dir, "small.mp4", "SMALL-BYTES");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("small.mp4", PROBE_SMALL);
        fixtures.put("small.mp4#2", PROBE_SMALL);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path output = dir.resolve("out").resolve("small.mp4");
        assertThatThrownBy(() -> service.normalize(input, output))
                .isInstanceOf(FfmpegService.FfmpegException.class)
                .hasMessageContaining("规格校验失败");
    }

    // ---------- normalizeAll 单段失败不污染整批 ----------

    @Test
    void normalizeAll_singleFailureDoesNotPoisonBatch(@TempDir Path dir) throws IOException {
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

        assertThat(reports).hasSize(3);
        assertThat(reports.get(0).status()).isEqualTo(SegmentStatus.OK_NATIVE);
        assertThat(reports.get(0).ok()).isTrue();
        assertThat(reports.get(1).status()).isEqualTo(SegmentStatus.FAILED);
        assertThat(reports.get(1).ok()).isFalse();
        assertThat(reports.get(1).errorMessage()).isNotNull().isNotBlank();
        assertThat(reports.get(2).status()).isEqualTo(SegmentStatus.OK_NATIVE);
        assertThat(reports.get(2).ok()).isTrue();
        assertThat(reports.get(0).output()).exists();
        assertThat(reports.get(2).output()).exists();
    }

    // ---------- sanitizeFileName（通过 normalizeAll 输出文件名间接验证） ----------

    @Test
    void normalizeAll_sanitizesWeirdFileNames(@TempDir Path dir) throws IOException {
        Path weird = writeInput(dir, "weird name@#$%.mp4", "W");
        Map<String, String> fixtures = new HashMap<>();
        fixtures.put("weird name@#$%.mp4", PROBE_HD);
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        Path workDir = Files.createDirectories(dir.resolve("work"));
        List<SegmentReport> reports = service.normalizeAll(List.of(weird), workDir);

        assertThat(reports).hasSize(1);
        assertThat(reports.get(0).ok()).isTrue();
        Path output = reports.get(0).output();
        String outName = output.getFileName().toString();
        assertThat(outName).startsWith("norm_0_");
        assertThat(outName).doesNotContain(" ").doesNotContain("@")
                .doesNotContain("#").doesNotContain("$").doesNotContain("%");
        assertThat(outName).contains("weird_name");
        assertThat(output).exists();
    }

    // ---------- 并发 ----------

    @Test
    void concurrentNormalizeAll_completesAndAllReportsAccountedFor(@TempDir Path dir) throws Exception {
        int threads = 4;
        Path workDir = Files.createDirectories(dir.resolve("work"));
        List<Path> inputs = new ArrayList<>();
        Map<String, String> fixtures = new HashMap<>();
        for (int i = 0; i < threads; i++) {
            Path p = writeInput(dir, "clip" + i + ".mp4", "C" + i);
            inputs.add(p);
            fixtures.put("clip" + i + ".mp4", PROBE_HD);
        }
        FakeCommandRunner runner = new FakeCommandRunner(fixtures);
        VideoNormalizationService service = newService(runner, new NoOpSuperResolutionProvider());

        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        List<List<SegmentReport>> results = new ArrayList<>();
        List<Throwable> errors = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            Path single = inputs.get(i);
            Thread t = new Thread(() -> {
                try {
                    start.await(5, TimeUnit.SECONDS);
                    List<SegmentReport> r = service.normalizeAll(List.of(single), workDir);
                    synchronized (results) {
                        results.add(r);
                    }
                } catch (Throwable ex) {
                    synchronized (errors) {
                        errors.add(ex);
                    }
                } finally {
                    done.countDown();
                }
            });
            t.start();
        }
        start.countDown();
        assertThat(done.await(15, TimeUnit.SECONDS)).isTrue();
        assertThat(errors).isEmpty();
        assertThat(results).hasSize(threads);
        for (List<SegmentReport> r : results) {
            assertThat(r).hasSize(1);
            assertThat(r.get(0).status()).isEqualTo(SegmentStatus.OK_NATIVE);
            assertThat(r.get(0).output()).exists();
        }
    }
}
