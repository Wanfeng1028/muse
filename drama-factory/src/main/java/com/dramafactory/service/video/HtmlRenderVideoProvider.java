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
 * poll() 检查 out/video.mp4。零 AI token 消耗，适合额度紧张时降级或特定风格
 * （kinetic typography、水彩剪影）。
 *
 * <p>支持双引擎（配置键 {@code drama.video.htmlrender.engine}）：
 * <ul>
 *   <li>{@code chromium}（默认）：无头 Chromium 逐帧截图 + ffmpeg 合成；</li>
 *   <li>{@code hyperframes}：调用 HyperFrames CLI（{@code hyperframes render ...}）确定性合成 MP4，
 *       复用配置键 {@code drama.video.hyperframes.cli}。</li>
 * </ul>
 * hyperframes 引擎探活失败或渲染失败时，<b>自动降级回 chromium</b> 并打 warn 日志——
 * 本 Provider 是降级通道，降级是正常行为，不抛错。
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

    @Value("${drama.video.htmlrender.engine:chromium}")
    private String engineConfig;

    @Value("${drama.video.hyperframes.cli:hyperframes}")
    private String hyperframesCli;

    private final CommandRunner commandRunner;

    private final ExecutorService executor = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "htmlrender-render");
        t.setDaemon(true);
        return t;
    });

    /**
     * Spring 用构造器：走默认 ProcessBuilder 命令执行器。
     */
    public HtmlRenderVideoProvider() {
        this(new ProcessBuilderCommandRunner());
    }

    /**
     * 测试缝构造器：注入命令执行器，其余配置取与 @Value 一致的默认值。
     */
    HtmlRenderVideoProvider(CommandRunner commandRunner) {
        this.commandRunner = commandRunner;
        this.workDirBase = "html-renders";
        this.htmlTemplateConfig = "scripts/html_scene_template.html";
        this.renderScriptConfig = "scripts/html_render.mjs";
        this.fps = 24;
        this.engineConfig = "chromium";
        this.hyperframesCli = "hyperframes";
    }

    /**
     * 渲染引擎枚举。
     */
    enum RenderEngine {
        CHROMIUM,
        HYPERFRAMES
    }

    /**
     * 命令执行器抽象（测试缝）。
     */
    interface CommandRunner {
        record ExecResult(int exitCode, String output) {}

        ExecResult run(List<String> command, Path workDir, long timeoutSeconds) throws IOException;
    }

    /**
     * 默认命令执行器：ProcessBuilder + 合并输出。
     */
    private static class ProcessBuilderCommandRunner implements CommandRunner {
        @Override
        public ExecResult run(List<String> command, Path workDir, long timeoutSeconds) throws IOException {
            Process process = new ProcessBuilder(command)
                    .directory(workDir != null ? workDir.toFile() : null)
                    .redirectErrorStream(true)
                    .start();
            StringBuilder output = new StringBuilder();
            Thread reader = new Thread(() -> {
                try (var in = process.getInputStream()) {
                    byte[] buf = new byte[4096];
                    int n;
                    while ((n = in.read(buf)) != -1) {
                        output.append(new String(buf, 0, n, StandardCharsets.UTF_8));
                    }
                } catch (IOException ignore) {
                }
            }, "htmlrender-cmd-reader");
            reader.setDaemon(true);
            reader.start();
            boolean done;
            try {
                done = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                process.destroyForcibly();
                Thread.currentThread().interrupt();
                throw new IOException("command interrupted: " + String.join(" ", command), e);
            }
            if (!done) {
                process.destroyForcibly();
                throw new IOException("command timeout after " + timeoutSeconds + "s: "
                        + String.join(" ", command));
            }
            try {
                reader.join(1000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            return new ExecResult(process.exitValue(), output.toString());
        }
    }

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

            RenderEngine engine = resolveEngine();

            log.info("[htmlrender] submit workDir={} seconds={} engine={} title={}", workDir, seconds,
                    engine, title.length() > 60 ? title.substring(0, 60) + "..." : title);

            final Path finalWorkDir = workDir;
            final int finalSeconds = seconds;
            executor.submit(() -> runRender(finalWorkDir, finalSeconds, engine));

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

    /**
     * 解析当前生效的渲染引擎。engine=chromium 时零开销，不探活 CLI。
     */
    RenderEngine resolveEngine() {
        String e = engineConfig == null ? "" : engineConfig.trim().toLowerCase();
        if (e.isEmpty() || "chromium".equals(e)) {
            return RenderEngine.CHROMIUM;
        }
        if ("hyperframes".equals(e)) {
            try {
                CommandRunner.ExecResult result = commandRunner.run(
                        List.of(hyperframesCli, "--version"),
                        Paths.get(System.getProperty("user.dir")),
                        15);
                if (result.exitCode() == 0) {
                    return RenderEngine.HYPERFRAMES;
                }
                log.warn("[htmlrender] hyperframes CLI 不可用（exit={}），降级为 chromium 引擎",
                        result.exitCode());
                return RenderEngine.CHROMIUM;
            } catch (Exception ex) {
                log.warn("[htmlrender] hyperframes CLI 不可用（{}），降级为 chromium 引擎",
                        ex.getMessage() != null ? ex.getMessage() : ex.getClass().getSimpleName());
                return RenderEngine.CHROMIUM;
            }
        }
        log.warn("[htmlrender] 未知的 engine 配置: {}，使用 chromium", engineConfig);
        return RenderEngine.CHROMIUM;
    }

    void setEngineConfig(String v) {
        this.engineConfig = v;
    }

    void setHyperframesCli(String v) {
        this.hyperframesCli = v;
    }

    void setWorkDirBase(String v) {
        this.workDirBase = v;
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

    private void runRender(Path workDir, int seconds, RenderEngine engine) {
        Path outDir = workDir.resolve("out");
        try {
            Files.createDirectories(outDir);
        } catch (IOException e) {
            log.error("[htmlrender] create outDir failed", e);
            return;
        }

        if (engine == RenderEngine.HYPERFRAMES) {
            try {
                Path sceneHtml = workDir.resolve("scene.html");
                String html = Files.readString(sceneHtml, StandardCharsets.UTF_8);
                Files.writeString(workDir.resolve("composition.html"), html, StandardCharsets.UTF_8);

                runHyperframesRender(workDir, seconds);
                log.info("[htmlrender] hyperframes done: {}", outDir.resolve("video.mp4"));
                return;
            } catch (Exception e) {
                log.warn("[htmlrender] hyperframes 引擎渲染失败，降级走 chromium 管道: {}",
                        e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName());
                // 继续走 chromium 管道
            }
        }

        try {
            runChromiumRender(workDir, seconds);
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

    /**
     * HyperFrames CLI 渲染分支。失败抛 IOException（由调用方降级）。
     */
    private void runHyperframesRender(Path workDir, int seconds) throws IOException {
        Path outDir = workDir.resolve("out");
        Files.createDirectories(outDir);

        List<String> cmd = new ArrayList<>();
        cmd.add(hyperframesCli);
        cmd.add("render");
        cmd.add("-c");
        cmd.add("composition.html");
        cmd.add("-o");
        cmd.add("out/video.mp4");
        cmd.add("--resolution");
        cmd.add("1080p");
        cmd.add("--fps");
        cmd.add(String.valueOf(fps));
        cmd.add("--no-browser-gpu");

        log.info("[htmlrender] hyperframes render: {}", String.join(" ", cmd));
        CommandRunner.ExecResult result = commandRunner.run(cmd, workDir, RENDER_TIMEOUT_MINUTES * 60);
        Path mp4 = outDir.resolve("video.mp4");
        if (result.exitCode() != 0) {
            String out = result.output() != null ? result.output() : "";
            if (out.length() > 200) {
                out = out.substring(0, 200);
            }
            throw new IOException("hyperframes render failed, exit=" + result.exitCode() + ", output=" + out);
        }
        if (!Files.exists(mp4)) {
            String out = result.output() != null ? result.output() : "";
            if (out.length() > 200) {
                out = out.substring(0, 200);
            }
            throw new IOException("hyperframes render produced no output mp4, output=" + out);
        }
    }

    /**
     * Chromium 逐帧截图 + ffmpeg 合成（原渲染管道）。
     */
    private void runChromiumRender(Path workDir, int seconds) throws IOException, InterruptedException {
        Path outDir = workDir.resolve("out");
        Path framesDir = workDir.resolve("frames");
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
