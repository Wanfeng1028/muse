package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * HTML 渲染视频 Provider（省 token 降级选项）。
 *
 * <p>与 PaintedAnimationVideoProvider 同模式：submit() 生成 HTML 文件并后台渲染，
 * poll() 检查 out/video.mp4。渲染用无头 Chromium 逐帧截图 + ffmpeg 合成，
 * 零 AI token 消耗，适合额度紧张时降级或特定风格（ kinetic typography、水彩剪影）。
 *
 * <p>在 VideoProviderRouter 链中位于 AI providers 之后，作为省钱兜底。
 */
@Component("htmlRenderVideoProvider")
public class HtmlRenderVideoProvider implements VideoProvider {

    private static final Logger log = LoggerFactory.getLogger(HtmlRenderVideoProvider.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String TASK_PREFIX = "htmlrender:";
    private static final long RENDER_TIMEOUT_MINUTES = 30;

    @Value("${drama.video.htmlrender.work-dir:html-renders}")
    private String workDirBase;

    @Value("${drama.video.htmlrender.template:scripts/html_scene_template.html}")
    private String htmlTemplateConfig;

    @Value("${drama.video.htmlrender.render-script:scripts/html_render.mjs}")
    private String renderScriptConfig;

    @Value("${drama.video.htmlrender.fps:24}")
    private int fps;

    private final ExecutorService executor = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "htmlrender-render");
        t.setDaemon(true);
        return t;
    });

    @Override
    public String name() {
        return "htmlrender";
    }

    @Override
    public String submit(Shot shot, int seconds) {
        try {
            Path baseDir = Paths.get(workDirBase).toAbsolutePath().normalize();
            Path workDir = baseDir.resolve("html-" + UUID.randomUUID()).normalize();
            if (!workDir.startsWith(baseDir)) {
                throw new RuntimeException("workDir escaped base directory: " + workDir);
            }
            Files.createDirectories(workDir);

            Path templatePath = resolvePath(htmlTemplateConfig);
            if (!Files.isRegularFile(templatePath)) {
                throw new RuntimeException("HTML template not found: " + templatePath);
            }

            String title = buildTitle(shot);
            String prompt = shot.getVideoPrompt() != null ? shot.getVideoPrompt() : "";
            String description = shot.getDescription() != null ? shot.getDescription() : "";

            String template = Files.readString(templatePath, StandardCharsets.UTF_8);
            String html = template
                    .replace("__TITLE__", htmlEscape(title))
                    .replace("__PROMPT__", htmlEscape(prompt))
                    .replace("__DESCRIPTION__", htmlEscape(description))
                    .replace("__DURATION__", Integer.toString(seconds))
                    .replace("__FPS__", Integer.toString(fps));

            Files.writeString(workDir.resolve("scene.html"), html, StandardCharsets.UTF_8);

            log.info("[htmlrender] submit workDir={} seconds={} title={}", workDir, seconds,
                    title.length() > 60 ? title.substring(0, 60) + "..." : title);

            final Path finalWorkDir = workDir;
            final int finalSeconds = seconds;
            executor.submit(() -> runRender(finalWorkDir, finalSeconds));

            return TASK_PREFIX + workDir.toAbsolutePath();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @Override
    public ProbeResult poll(String providerTaskId) {
        if (providerTaskId == null || !providerTaskId.startsWith(TASK_PREFIX)) {
            return new ProbeResult(RemoteStatus.FAILED, null,
                    "invalid providerTaskId format", 0);
        }
        String pathStr = providerTaskId.substring(TASK_PREFIX.length());
        Path workDir;
        try {
            workDir = Paths.get(pathStr).toAbsolutePath().normalize();
        } catch (Exception e) {
            return new ProbeResult(RemoteStatus.FAILED, null,
                    "invalid workDir path: " + pathStr, 0);
        }
        Path outDir = workDir.resolve("out");
        Path mp4 = outDir.resolve("video.mp4");
        Path failedFlag = outDir.resolve("FAILED");
        if (Files.exists(mp4)) {
            return new ProbeResult(RemoteStatus.COMPLETED,
                    "file://" + mp4.toAbsolutePath(), null, 100);
        }
        if (Files.exists(failedFlag)) {
            String detail = "";
            try {
                detail = Files.readString(failedFlag, StandardCharsets.UTF_8);
                if (detail.length() > 200) {
                    detail = detail.substring(0, 200);
                }
            } catch (Exception ignore) {
                detail = "渲染失败";
            }
            return new ProbeResult(RemoteStatus.FAILED, null, detail, 0);
        }
        return new ProbeResult(RemoteStatus.PROCESSING, null, null, 0);
    }

    private Path resolvePath(String config) {
        Path p = Paths.get(config);
        if (!p.isAbsolute()) {
            p = Paths.get(System.getProperty("user.dir")).resolve(p);
        }
        return p.toAbsolutePath().normalize();
    }

    private String buildTitle(Shot shot) {
        String t = shot.getDescription();
        if (t == null || t.isBlank()) {
            t = shot.getVideoPrompt();
        }
        if (t == null || t.isBlank()) {
            t = "未命名镜头";
        }
        return t.strip();
    }

    private String htmlEscape(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");
    }

    private void runRender(Path workDir, int seconds) {
        Path outDir = workDir.resolve("out");
        Path framesDir = workDir.resolve("frames");
        try {
            Files.createDirectories(outDir);
            Files.createDirectories(framesDir);

            Path renderScript = resolvePath(renderScriptConfig);
            if (!Files.isRegularFile(renderScript)) {
                throw new IOException("render script not found: " + renderScript);
            }

            // Step 1: Node + playwright 逐帧截图
            List<String> captureCmd = new ArrayList<>();
            captureCmd.add("node");
            captureCmd.add(renderScript.toString());
            captureCmd.add(workDir.resolve("scene.html").toString());
            captureCmd.add(framesDir.toString());
            captureCmd.add(Integer.toString(seconds));
            captureCmd.add(Integer.toString(fps));

            log.info("[htmlrender] capturing frames: {}", String.join(" ", captureCmd));
            Process capture = new ProcessBuilder(captureCmd)
                    .directory(workDir.toFile())
                    .redirectErrorStream(true)
                    .start();
            boolean done = capture.waitFor(RENDER_TIMEOUT_MINUTES, TimeUnit.MINUTES);
            if (!done) {
                capture.destroyForcibly();
                throw new IOException("frame capture timeout after " + RENDER_TIMEOUT_MINUTES + "min");
            }
            if (capture.exitValue() != 0) {
                throw new IOException("frame capture failed, exit=" + capture.exitValue());
            }

            // Step 2: ffmpeg 合成 mp4
            List<String> ffmpegCmd = new ArrayList<>();
            ffmpegCmd.add("ffmpeg");
            ffmpegCmd.add("-y");
            ffmpegCmd.add("-framerate");
            ffmpegCmd.add(Integer.toString(fps));
            ffmpegCmd.add("-i");
            ffmpegCmd.add(framesDir.resolve("frame-%04d.png").toString());
            ffmpegCmd.add("-c:v");
            ffmpegCmd.add("libx264");
            ffmpegCmd.add("-pix_fmt");
            ffmpegCmd.add("yuv420p");
            ffmpegCmd.add("-crf");
            ffmpegCmd.add("20");
            ffmpegCmd.add(outDir.resolve("video.mp4").toString());

            log.info("[htmlrender] assembling mp4");
            Process ffmpeg = new ProcessBuilder(ffmpegCmd)
                    .redirectErrorStream(true)
                    .start();
            done = ffmpeg.waitFor(10, TimeUnit.MINUTES);
            if (!done) {
                ffmpeg.destroyForcibly();
                throw new IOException("ffmpeg timeout");
            }
            if (ffmpeg.exitValue() != 0) {
                throw new IOException("ffmpeg failed, exit=" + ffmpeg.exitValue());
            }

            log.info("[htmlrender] done: {}", outDir.resolve("video.mp4"));
        } catch (Exception e) {
            log.error("[htmlrender] render failed", e);
            try {
                Files.writeString(outDir.resolve("FAILED"),
                        e.getMessage() != null ? e.getMessage() : "unknown error",
                        StandardCharsets.UTF_8);
            } catch (IOException ignore) {
            }
        }
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
