package com.dramafactory.service;

import com.dramafactory.service.FfmpegService.FfmpegException;
import com.dramafactory.service.FfmpegService.FfmpegInterruptedException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;

/**
 * 剧坊成片标准化服务。
 *
 * <p>将各家视频模型输出的分辨率/帧率/编码各不相同的分镜片段，统一转码为拼接前所需的规格，
 * 避免音画问题与"画面糊"。核心流程：探测 → 达标判定 → （可选超分）→ ffmpeg 转码 → 校验。</p>
 */
@Service
public class VideoNormalizationService {

    private static final Logger log = LoggerFactory.getLogger(VideoNormalizationService.class);

    /**
     * 外部命令执行器（生产走 FfmpegService.executeCapture，测试注入 fake）。
     */
    public interface CommandRunner {
        String run(List<String> command, long timeoutSeconds);
    }

    /**
     * 适配模式。
     */
    public enum FitMode {
        /** 保持宽高比 + 黑边。 */
        PAD,
        /** 保持宽高比 + 居中裁剪。 */
        CROP
    }

    /**
     * 片段处理状态。
     */
    public enum SegmentStatus {
        /** 原生规格已达标，仅拷贝。 */
        OK_NATIVE,
        /** 已转码。 */
        OK_TRANSCODED,
        /** 失败。 */
        FAILED
    }

    /**
     * 单段处理报告。
     */
    public record SegmentReport(Path input, Path output, SegmentStatus status, boolean upsampled,
                                int sourceWidth, int sourceHeight, String errorMessage) {
        public boolean ok() {
            return status != SegmentStatus.FAILED;
        }
    }

    /**
     * 探测得到的源信息。
     */
    public record SourceInfo(int width, int height, double fps, String videoCodec, String pixFmt,
                             boolean hasAudio, String audioCodec) {
    }

    private final CommandRunner runner;
    private final ObjectMapper objectMapper;
    private final SuperResolutionProvider superResolutionProvider;
    private final boolean enabled;
    private final int width;
    private final int height;
    private final double fps;
    private final int crf;
    private final FitMode fitMode;
    private final long timeoutSeconds;
    private final int retryAttempts;
    private final String ffprobeBinary;
    private final String ffmpegBinary;

    /**
     * 生产构造器（Spring 用）。
     */
    @Autowired
    public VideoNormalizationService(FfmpegService ffmpegService,
                                     ObjectMapper objectMapper,
                                     SuperResolutionProvider superResolutionProvider,
                                     @Value("${drama.normalize.enabled:true}") boolean enabled,
                                     @Value("${drama.normalize.width:1280}") int width,
                                     @Value("${drama.normalize.height:720}") int height,
                                     @Value("${drama.normalize.fps:30}") double fps,
                                     @Value("${drama.normalize.crf:20}") int crf,
                                     @Value("${drama.normalize.fit-mode:pad}") String fitMode,
                                     @Value("${drama.normalize.timeout-seconds:600}") long timeoutSeconds,
                                     @Value("${drama.normalize.retry-attempts:2}") int retryAttempts) {
        this((cmd, t) -> ffmpegService.executeCapture(cmd, t),
                objectMapper,
                superResolutionProvider,
                ffmpegService.getFfmpeg(),
                ffmpegService.getFfprobe(),
                enabled,
                width,
                height,
                fps,
                crf,
                parseFitMode(fitMode),
                timeoutSeconds,
                retryAttempts);
    }

    /**
     * 测试构造器（包可见，不许 public）。
     */
    VideoNormalizationService(CommandRunner runner, ObjectMapper objectMapper,
                              SuperResolutionProvider superResolutionProvider,
                              String ffmpegBinary, String ffprobeBinary,
                              boolean enabled, int width, int height, double fps, int crf,
                              FitMode fitMode, long timeoutSeconds, int retryAttempts) {
        if (width <= 0 || width % 2 != 0) {
            throw new IllegalArgumentException("width 必须为正偶数: " + width);
        }
        if (height <= 0 || height % 2 != 0) {
            throw new IllegalArgumentException("height 必须为正偶数: " + height);
        }
        if (fps <= 0) {
            throw new IllegalArgumentException("fps 必须为正: " + fps);
        }
        if (crf < 0 || crf > 51) {
            throw new IllegalArgumentException("crf 必须在 0..51 之间: " + crf);
        }
        this.runner = runner;
        this.objectMapper = objectMapper;
        this.superResolutionProvider = superResolutionProvider;
        this.enabled = enabled;
        this.width = width;
        this.height = height;
        this.fps = fps;
        this.crf = crf;
        this.fitMode = fitMode;
        this.timeoutSeconds = timeoutSeconds;
        this.retryAttempts = retryAttempts;
        this.ffprobeBinary = ffprobeBinary;
        this.ffmpegBinary = ffmpegBinary;
    }

    private static FitMode parseFitMode(String raw) {
        if (raw != null && "crop".equalsIgnoreCase(raw.trim())) {
            return FitMode.CROP;
        }
        return FitMode.PAD;
    }

    /**
     * 是否启用标准化。
     */
    public boolean isEnabled() {
        return enabled;
    }

    /**
     * 探测源文件信息。
     */
    SourceInfo probe(Path input) {
        List<String> command = List.of(
                ffprobeBinary,
                "-v", "error",
                "-show_streams",
                "-show_format",
                "-of", "json",
                input.toString());
        String json = runner.run(command, 60L);
        try {
            JsonNode root = objectMapper.readTree(json);
            JsonNode streams = root.path("streams");
            int vw = -1;
            int vh = -1;
            double vfps = -1;
            String vcodec = null;
            String pixFmt = null;
            boolean hasVideo = false;
            boolean hasAudio = false;
            String acodec = null;
            for (JsonNode stream : streams) {
                String type = stream.path("codec_type").asText("");
                if ("video".equals(type) && !hasVideo) {
                    hasVideo = true;
                    vw = stream.path("width").asInt(-1);
                    vh = stream.path("height").asInt(-1);
                    vfps = parseFrameRate(stream.path("avg_frame_rate").asText(""));
                    vcodec = stream.path("codec_name").asText(null);
                    pixFmt = stream.path("pix_fmt").asText(null);
                } else if ("audio".equals(type) && !hasAudio) {
                    hasAudio = true;
                    acodec = stream.path("codec_name").asText(null);
                }
            }
            if (!hasVideo) {
                throw new FfmpegException("未探测到视频流", false);
            }
            return new SourceInfo(vw, vh, vfps, vcodec, pixFmt, hasAudio, acodec);
        } catch (IOException e) {
            throw new FfmpegException("解析 ffprobe 输出失败: " + e.getMessage(), false);
        }
    }

    private static double parseFrameRate(String rate) {
        if (rate == null || rate.isEmpty()) {
            return -1;
        }
        int slash = rate.indexOf('/');
        if (slash <= 0) {
            try {
                return Double.parseDouble(rate);
            } catch (NumberFormatException e) {
                return -1;
            }
        }
        try {
            double num = Double.parseDouble(rate.substring(0, slash));
            double den = Double.parseDouble(rate.substring(slash + 1));
            if (den == 0) {
                return -1;
            }
            return num / den;
        } catch (NumberFormatException e) {
            return -1;
        }
    }

    /**
     * 判断源是否已符合目标规格。
     */
    boolean conforms(SourceInfo s) {
        if (s.width() != width || s.height() != height) {
            return false;
        }
        if (s.fps() <= 0 || Math.abs(s.fps() - fps) >= 0.02) {
            return false;
        }
        if (!"h264".equals(s.videoCodec())) {
            return false;
        }
        if (!"yuv420p".equals(s.pixFmt())) {
            return false;
        }
        if (s.hasAudio() && !"aac".equals(s.audioCodec())) {
            return false;
        }
        return true;
    }

    /**
     * 归一化单个片段。
     */
    public SegmentReport normalize(Path input, Path output) {
        if (input == null) {
            throw new IllegalArgumentException("input 不能为 null");
        }
        if (!Files.exists(input) || !Files.isRegularFile(input)) {
            throw new IllegalArgumentException("input 不存在或非普通文件: " + input);
        }
        Path outputParent = output.toAbsolutePath().getParent();
        if (outputParent == null) {
            throw new IllegalArgumentException("output 缺少父目录: " + output);
        }
        if (!Files.exists(outputParent)) {
            try {
                Files.createDirectories(outputParent);
            } catch (IOException e) {
                throw new FfmpegException("创建输出目录失败: " + e.getMessage(), false);
            }
        }

        SourceInfo src = probe(input);
        int srcW = src.width();
        int srcH = src.height();
        boolean upsampled = srcW < width || srcH < height;

        if (conforms(src)) {
            try {
                Files.copy(input, output, StandardCopyOption.REPLACE_EXISTING);
            } catch (IOException e) {
                throw new FfmpegException("拷贝原生达标文件失败: " + e.getMessage(), false);
            }
            log.info("片段规格原生达标，直接拷贝: {} -> {}", input.getFileName(), output.getFileName());
            return new SegmentReport(input, output, SegmentStatus.OK_NATIVE, false, srcW, srcH, null);
        }

        Path transcodeSource = input;
        if (upsampled) {
            if (superResolutionProvider != null && superResolutionProvider.isAvailable()) {
                Path enhanced = superResolutionProvider.enhance(input, output.getParent());
                if (enhanced != null) {
                    transcodeSource = enhanced;
                    log.info("对 {} 使用超分能力增强后再转码", input.getFileName());
                }
            } else {
                log.warn("超分能力不可用，对 {} 使用普通升采样（非真超分）", input.getFileName());
            }
        }
        if (upsampled) {
            log.warn("{} 已升采样（非原生），源 {}x{} -> 目标 {}x{}",
                    input.getFileName(), srcW, srcH, width, height);
        }

        List<String> command = buildTranscodeCommand(transcodeSource, output);
        runWithRetry(command);
        verify(output);
        log.info("片段转码完成: {} -> {}", input.getFileName(), output.getFileName());
        return new SegmentReport(input, output, SegmentStatus.OK_TRANSCODED, upsampled, srcW, srcH, null);
    }

    private List<String> buildTranscodeCommand(Path source, Path output) {
        String videoFilter;
        if (fitMode == FitMode.CROP) {
            videoFilter = "scale=" + width + ":" + height
                    + ":force_original_aspect_ratio=increase,crop=" + width + ":" + height;
        } else {
            videoFilter = "scale=" + width + ":" + height
                    + ":force_original_aspect_ratio=decrease,pad=" + width + ":" + height
                    + ":(ow-iw)/2:(oh-ih)/2:color=black";
        }
        List<String> command = new ArrayList<>();
        command.add(ffmpegBinary);
        command.add("-y");
        command.add("-i");
        command.add(source.toString());
        command.add("-vf");
        command.add(videoFilter);
        command.add("-r");
        command.add(String.valueOf((int) fps));
        command.add("-c:v");
        command.add("libx264");
        command.add("-pix_fmt");
        command.add("yuv420p");
        command.add("-crf");
        command.add(String.valueOf(crf));
        command.add("-preset");
        command.add("veryfast");
        command.add("-c:a");
        command.add("aac");
        command.add("-ar");
        command.add("44100");
        command.add("-ac");
        command.add("2");
        command.add(output.toString());
        return command;
    }

    private void runWithRetry(List<String> command) {
        int attempts = Math.max(0, retryAttempts);
        int attempt = 0;
        while (true) {
            try {
                runner.run(command, timeoutSeconds);
                return;
            } catch (FfmpegException e) {
                if (!e.isTransient() || attempt >= attempts) {
                    throw e;
                }
                attempt++;
                log.warn("转码瞬时失败，第 {} 次重试: {}", attempt, e.getMessage());
                try {
                    Thread.sleep(1000L);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new FfmpegInterruptedException("转码重试等待被中断", ie);
                }
            }
        }
    }

    private void verify(Path output) {
        List<String> command = List.of(
                ffprobeBinary,
                "-v", "error",
                "-show_streams",
                "-show_format",
                "-of", "json",
                output.toString());
        String json = runner.run(command, 60L);
        try {
            JsonNode root = objectMapper.readTree(json);
            JsonNode streams = root.path("streams");
            int vw = -1;
            int vh = -1;
            String vcodec = null;
            String pixFmt = null;
            boolean hasVideo = false;
            for (JsonNode stream : streams) {
                if ("video".equals(stream.path("codec_type").asText("")) && !hasVideo) {
                    hasVideo = true;
                    vw = stream.path("width").asInt(-1);
                    vh = stream.path("height").asInt(-1);
                    vcodec = stream.path("codec_name").asText(null);
                    pixFmt = stream.path("pix_fmt").asText(null);
                }
            }
            double duration = root.path("format").path("duration").asDouble(-1);
            if (vw != width || vh != height) {
                throw new FfmpegException("规格校验失败: 分辨率 " + vw + "x" + vh
                        + " != " + width + "x" + height, false);
            }
            if (duration <= 0) {
                throw new FfmpegException("规格校验失败: duration 无效 " + duration, false);
            }
            if (vcodec == null || !vcodec.contains("264")) {
                throw new FfmpegException("规格校验失败: 视频编码 " + vcodec, false);
            }
            if (!"yuv420p".equals(pixFmt)) {
                throw new FfmpegException("规格校验失败: 像素格式 " + pixFmt, false);
            }
        } catch (IOException e) {
            throw new FfmpegException("校验解析 ffprobe 输出失败: " + e.getMessage(), false);
        }
    }

    /**
     * 批量归一化。单段失败不污染整批。
     */
    public List<SegmentReport> normalizeAll(List<Path> inputs, Path workDir) {
        if (inputs == null || inputs.isEmpty()) {
            throw new IllegalArgumentException("inputs 不能为空");
        }
        try {
            Files.createDirectories(workDir);
        } catch (IOException e) {
            throw new FfmpegException("创建 workDir 失败: " + e.getMessage(), false);
        }
        List<SegmentReport> reports = new ArrayList<>();
        for (int i = 0; i < inputs.size(); i++) {
            Path input = inputs.get(i);
            String rawName = input == null || input.getFileName() == null
                    ? "unknown" : input.getFileName().toString();
            String outName = "norm_" + i + "_" + sanitizeFileName(rawName);
            Path output = workDir.resolve(outName);
            try {
                reports.add(normalize(input, output));
            } catch (Exception e) {
                log.error("片段归一化失败: {} -> {}", input, output, e);
                reports.add(new SegmentReport(input, output, SegmentStatus.FAILED, false, -1, -1,
                        e.getMessage()));
            }
        }
        return reports;
    }

    private static String sanitizeFileName(String name) {
        if (name == null || name.isEmpty()) {
            return "unknown";
        }
        return name.replaceAll("[^a-zA-Z0-9._-]", "_");
    }
}
