
package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * 剧坊 HTML 渲染降级路线：调用 HyperFrames CLI 把 composition.html 逐帧渲染成 MP4。
 * 模板二选一：shot-card（默认，单卡片 kinetic 排版）或 shot-timeline（多节拍时间线：bg/title/subtitle/accent 四个可寻址 clip）；非法值在 submit 时直接拒绝。
 * 本 VM 无 GPU，默认追加 --no-browser-gpu 走 CPU 渲染。
 */
@Component("hyperFramesVideoProvider")
public class HyperFramesVideoProvider implements VideoProvider {

    private static final Logger log = LoggerFactory.getLogger(HyperFramesVideoProvider.class);
    private static final String TASK_PREFIX = "hyperframes:";
    private static final int TITLE_MAX = 60;
    private static final int ERR_MAX = 200;
    private static final int FAILED_MAX = 500;
    private static final long VERSION_TIMEOUT_SECONDS = 15;

    @Value("${drama.video.hyperframes.enabled:true}")
    private boolean enabled;

    @Value("${drama.video.hyperframes.cli:hyperframes}")
    private String cli;

    @Value("${drama.video.hyperframes.work-dir:hyperframes-renders}")
    private String workDirBase;

    @Value("${drama.video.hyperframes.resolution:1080p}")
    private String resolution;

    @Value("${drama.video.hyperframes.fps:24}")
    private int fps;

    @Value("${drama.video.hyperframes.workers:2}")
    private int workers;

    @Value("${drama.video.hyperframes.timeout-minutes:30}")
    private long timeoutMinutes;

    @Value("${drama.video.hyperframes.browser-gpu:false}")
    private boolean browserGpu;

    @Value("${drama.video.hyperframes.template:shot-card}")
    private String template;

    private final CommandRunner commandRunner;

    private final ExecutorService executor = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "hyperframes-render");
        t.setDaemon(true);
        return t;
    });

    /** Spring 使用的无参构造，命令执行走默认 ProcessBuilder 实现。 */
    public HyperFramesVideoProvider() {
        this(new ProcessBuilderCommandRunner());
    }

    /** 测试缝：注入 fake CommandRunner 覆盖全部路径，无需真实 CLI；配置字段取与 @Value 一致的默认值。 */
    HyperFramesVideoProvider(CommandRunner commandRunner) {
        this.commandRunner = commandRunner;
        this.enabled = true;
        this.cli = "hyperframes";
        this.workDirBase = "hyperframes-renders";
        this.resolution = "1080p";
        this.fps = 24;
        this.workers = 2;
        this.timeoutMinutes = 30;
        this.browserGpu = false;
        this.template = "shot-card";
    }

    @Override
    public String name() {
        return "hyperframes";
    }

    @Override
    public String submit(Shot shot, int seconds) {
        if (!enabled) {
            throw new IllegalStateException("hyperframes 通道未启用（drama.video.hyperframes.enabled=false）");
        }
        if (seconds <= 0) {
            throw new IllegalArgumentException("seconds 必须为正数，实际：" + seconds);
        }
        if (!"shot-card".equals(template) && !"shot-timeline".equals(template)) {
            throw new IllegalArgumentException(
                    "hyperframes 模板非法：" + template + "，只允许 shot-card 或 shot-timeline");
        }

        // 1) 先自检 CLI 可用性（--version，15 秒超时）
        ensureCliAvailable();

        try {
            Path baseDir = Paths.get(workDirBase).toAbsolutePath().normalize();
            Path workDir = baseDir.resolve("hyperframes-" + UUID.randomUUID()).normalize();
            if (!workDir.startsWith(baseDir)) {
                throw new RuntimeException("workDir escaped base directory: " + workDir);
            }
            Files.createDirectories(workDir);
            Path outDir = workDir.resolve("out");
            Files.createDirectories(outDir);

            // 2) 写自包含 composition.html（不引用任何外部资源）
            String html = "shot-timeline".equals(template)
                    ? buildTimelineCompositionHtml(shot, seconds)
                    : buildCompositionHtml(shot, seconds);
            Files.write(workDir.resolve("composition.html"), html.getBytes(StandardCharsets.UTF_8));

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
            return new ProbeResult(RemoteStatus.FAILED, null, "invalid providerTaskId format", 0);
        }
        String pathStr = providerTaskId.substring(TASK_PREFIX.length());
        Path workDir;
        try {
            workDir = Paths.get(pathStr).toAbsolutePath().normalize();
        } catch (Exception e) {
            return new ProbeResult(RemoteStatus.FAILED, null, "invalid workDir path", 0);
        }

        Path mp4 = workDir.resolve("out").resolve("video.mp4");
        if (Files.isRegularFile(mp4)) {
            String url = mp4.toUri().toString();
            return new ProbeResult(RemoteStatus.COMPLETED, url, null, 100);
        }

        Path failed = workDir.resolve("out").resolve("FAILED");
        if (Files.isRegularFile(failed)) {
            String reason;
            try {
                reason = truncate(Files.readString(failed), 200);
            } catch (Exception e) {
                reason = "渲染失败";
            }
            if (reason == null || reason.isBlank()) {
                reason = "渲染失败";
            }
            return new ProbeResult(RemoteStatus.FAILED, null, reason, 0);
        }

        return new ProbeResult(RemoteStatus.PROCESSING, null, null, 0);
    }

    @Override
    public ConnectivityResult probeConnectivity() {
        try {
            CommandRunner.ExecResult result =
                    commandRunner.run(List.of(cli, "--version"), Paths.get(System.getProperty("user.dir")), 15);
            if (result.exitCode() == 0) {
                return new ConnectivityResult(ConnectivityStatus.OK, "hyperframes CLI 就绪");
            }
            String detail = result.output() == null ? "" : truncate(result.output(), 200);
            if (detail.isBlank()) {
                detail = "hyperframes CLI 返回非零退出码：" + result.exitCode();
            }
            return new ConnectivityResult(ConnectivityStatus.UNREACHABLE, detail);
        } catch (Exception e) {
            String msg = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            return new ConnectivityResult(ConnectivityStatus.UNREACHABLE, truncate(msg, 200));
        }
    }

    private void ensureCliAvailable() {
        try {
            CommandRunner.ExecResult result =
                    commandRunner.run(List.of(cli, "--version"), Paths.get(System.getProperty("user.dir")), 15);
            if (result.exitCode() != 0) {
                String detail = result.output() == null ? "" : truncate(result.output(), 200);
                throw new RuntimeException("hyperframes CLI 不可用：" + detail
                        + "，请安装 Node.js 22+ 并执行 npm i -g hyperframes");
            }
        } catch (RuntimeException re) {
            throw re;
        } catch (Exception e) {
            String msg = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            throw new RuntimeException("hyperframes CLI 不可用：" + truncate(msg, 200)
                    + "，请安装 Node.js 22+ 并执行 npm i -g hyperframes");
        }
    }

    private String buildCompositionHtml(Shot shot, int seconds) {
        String title = htmlEscape(buildTitle(shot));
        String subtitle = htmlEscape("SHOT " + shot.getShotNo() + " · " + seconds + "s");
        StringBuilder sb = new StringBuilder();
        sb.append("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><style>");
        sb.append("*{margin:0;padding:0;box-sizing:border-box;}");
        sb.append("html,body{width:100%;height:100%;overflow:hidden;background:#05060a;}");
        sb.append("#root{position:relative;width:1920px;height:1080px;overflow:hidden;");
        sb.append("font-family:'PingFang SC','Microsoft YaHei',system-ui,sans-serif;}");
        sb.append(".bg{position:absolute;inset:0;");
        sb.append("background:radial-gradient(circle at 50% 45%,#1b2440 0%,#0b0f1c 55%,#04060c 100%);}");
        sb.append(".bgzoom{animation:bgzoom ").append(seconds).append("s linear both;}");
        sb.append("@keyframes bgzoom{from{transform:scale(1.0);}to{transform:scale(1.18);}}");
        sb.append(".stack{position:absolute;inset:0;display:flex;flex-direction:column;");
        sb.append("align-items:center;justify-content:center;gap:28px;padding:0 120px;text-align:center;}");
        sb.append(".title{color:#f5f8ff;font-size:96px;font-weight:700;line-height:1.2;");
        sb.append("letter-spacing:2px;text-shadow:0 8px 40px rgba(0,0,0,0.65);}");
        sb.append(".rise{animation:rise ").append(seconds).append("s ease-out both;}");
        sb.append("@keyframes rise{from{opacity:0;transform:translateY(48px);}");
        sb.append("to{opacity:1;transform:translateY(0);}}");
        sb.append(".subtitle{color:#8fa6d8;font-size:34px;font-weight:500;letter-spacing:6px;}");
        sb.append(".clip{will-change:transform,opacity;}");
        sb.append("</style></head><body>");
        sb.append("<div id=\"root\" data-composition-id=\"shot-card\" data-width=\"1920\" ");
        sb.append("data-height=\"1080\" data-start=\"0\">");
        sb.append("<div class=\"bg bgzoom clip\" data-start=\"0\" data-duration=\"")
                .append(seconds).append("\"></div>");
        sb.append("<div class=\"stack\">");
        sb.append("<div class=\"title rise clip\" data-start=\"0\" data-duration=\"")
                .append(seconds).append("\">").append(title).append("</div>");
        sb.append("<div class=\"subtitle rise clip\" data-start=\"0\" data-duration=\"")
                .append(seconds).append("\">").append(subtitle).append("</div>");
        sb.append("</div></div></body></html>");
        return sb.toString();
    }

    private String htmlEscape(String s) {
        if (s == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(s.length() + 16);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '&' -> sb.append("&amp;");
                case '<' -> sb.append("&lt;");
                case '>' -> sb.append("&gt;");
                case '"' -> sb.append("&quot;");
                case '\'' -> sb.append("&#39;");
                default -> sb.append(c);
            }
        }
        return sb.toString();
    }

    private String buildTitle(Shot shot) {
        String title = shot.getDescription();
        if (title == null || title.isBlank()) {
            title = shot.getVideoPrompt();
        }
        if (title == null || title.isBlank()) {
            title = "未命名镜头";
        }
        title = title.strip();
        if (title.isEmpty()) {
            title = "未命名镜头";
        }
        if (title.length() > 60) {
            title = title.substring(0, 60);
        }
        return title;
    }

    private String buildTimelineCompositionHtml(Shot shot, int seconds) {
        int s = seconds;
        int titleDuration = Math.max(1, (2 * s) / 3);
        int subtitleStart = s / 3;
        int subtitleDuration = s - s / 3;
        int accentStart = (2 * s) / 3;
        int accentDuration = s - (2 * s) / 3;
        String titleText = htmlEscape(buildTitle(shot));
        String subtitleText = htmlEscape("SHOT " + shot.getShotNo() + " · " + s + "s");
        return "<!DOCTYPE html>" +
            "<html lang=\"zh-CN\">" +
            "<meta charset=\"UTF-8\">" +
            "<style>" +
            "*{margin:0;padding:0;box-sizing:border-box;}" +
        "html,body{width:1920px;height:1080px;overflow:hidden;background:#111;}" +
            "#root{position:relative;width:1920px;height:1080px;}" +
            ".clip{position:absolute;width:100%;height:100%;}" +
            ".clip-bg{background:#1a1a2e;animation:bgZoom linear both;}" +
            ".clip-title{display:flex;justify-content:center;align-items:center;padding-bottom:90px;animation:titleIn ease-out both;}" +
            ".clip-title span{font-size:72px;color:#fff;font-weight:bold;}" +
            ".clip-subtitle{display:flex;justify-content:center;align-items:center;padding-top:90px;animation:subIn ease-out both;}" +
            ".clip-subtitle span{font-size:36px;color:#aaa;}" +
            ".clip-accent{bottom:0;height:6px;background:#e94560;animation:accentGrow linear both;}" +
            "@keyframes bgZoom{from{transform:scale(1)}to{transform:scale(1.08)}}" +
            "@keyframes titleIn{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}" +
            "@keyframes subIn{from{opacity:0}to{opacity:1}}" +
            "@keyframes accentGrow{from{width:0}to{width:100%}}" +
            "</style>" +
            "<body>" +
            "<div id=\"root\" data-composition-id=\"shot-timeline\" data-width=\"1920\" data-height=\"1080\" data-start=\"0\" data-duration=\"" + s + "\">" +
            "<div class=\"clip clip-bg\" data-clip=\"bg\" data-start=\"0\" data-duration=\"" + s + "\" style=\"animation-duration:" + s + "s\"></div>" +
            "<div class=\"clip clip-title\" data-clip=\"title\" data-start=\"0\" data-duration=\"" + titleDuration + "\" style=\"animation-duration:" + titleDuration + "s\"><span>" + titleText + "</span></div>" +
            "<div class=\"clip clip-subtitle\" data-clip=\"subtitle\" data-start=\"" + subtitleStart + "\" data-duration=\"" + subtitleDuration + "\" style=\"animation-duration:" + subtitleDuration + "s\"><span>" + subtitleText + "</span></div>" +
            "<div class=\"clip clip-accent\" data-clip=\"accent\" data-start=\"" + accentStart + "\" data-duration=\"" + accentDuration + "\" style=\"animation-duration:" + accentDuration + "s\">" +
            "</div>" +
            "</div>" +
            "</body>" +
            "</html>";
    }

    private void runRender(Path workDir, int seconds) {
        List<String> cmd = new ArrayList<>();
        cmd.add(cli);
        cmd.add("render");
        cmd.add("-c");
        cmd.add("composition.html");
        cmd.add("-o");
        cmd.add("out/video.mp4");
        cmd.add("--resolution");
        cmd.add(resolution);
        cmd.add("--fps");
        cmd.add(String.valueOf(fps));
        cmd.add("--workers");
        cmd.add(String.valueOf(workers));
        if (!browserGpu) {
            cmd.add("--no-browser-gpu");
        }

        String failure = null;
        try {
            CommandRunner.ExecResult result =
                    commandRunner.run(cmd, workDir, (long) timeoutMinutes * 60L);
            if (result.exitCode() != 0) {
                String out = result.output() == null ? "" : result.output();
                failure = "hyperframes render 退出码 " + result.exitCode() + "：" + out;
            } else if (!Files.isRegularFile(workDir.resolve("out").resolve("video.mp4"))) {
                failure = "hyperframes render 结束但未生成 out/video.mp4";
            }
        } catch (Exception e) {
            String msg = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            failure = "hyperframes render 异常：" + msg;
        }

        if (failure != null) {
            try {
                Path outDir = workDir.resolve("out");
                Files.createDirectories(outDir);
                Files.writeString(outDir.resolve("FAILED"), truncate(failure, 500));
            } catch (Exception ignored) {
                // 标记写入失败时忽略，poll 会因缺少 mp4 而返回 PROCESSING
            }
        }
    }

    private static String truncate(String s, int n) {
        if (s == null) {
            return "";
        }
        if (s.length() <= n) {
            return s;
        }
        return s.substring(0, n);
    }

    @FunctionalInterface
    public interface CommandRunner {
        record ExecResult(int exitCode, String output) {}

        ExecResult run(List<String> command, Path workDir, long timeoutSeconds) throws IOException;
    }

    private static class ProcessBuilderCommandRunner implements CommandRunner {
        @Override
        public ExecResult run(List<String> command, Path workDir, long timeoutSeconds) throws IOException {
            ProcessBuilder pb = new ProcessBuilder(command);
            pb.redirectErrorStream(true);
            if (workDir != null) {
                pb.directory(workDir.toFile());
            }
            Process proc = pb.start();
            boolean finished;
            try {
                finished = proc.waitFor(timeoutSeconds, TimeUnit.SECONDS);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                proc.destroyForcibly();
                throw new IOException("命令被中断: " + command.get(0), ie);
            }
            if (!finished) {
                proc.destroyForcibly();
                throw new IOException("命令超时（" + timeoutSeconds + "s）: " + command.get(0));
            }
            String output;
            try (InputStream in = proc.getInputStream()) {
                output = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            }
            return new ExecResult(proc.exitValue(), output);
        }
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdownNow();
    }
}
