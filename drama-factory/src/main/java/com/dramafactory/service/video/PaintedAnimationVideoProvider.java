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
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

@Component("paintedAnimationVideoProvider")
public class PaintedAnimationVideoProvider implements VideoProvider {

    private static final Logger log = LoggerFactory.getLogger(PaintedAnimationVideoProvider.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String TASK_PREFIX = "painted:";
    private static final long RENDER_TIMEOUT_MINUTES = 30;

    @Value("${drama.video.painted.work-dir:painted-renders}")
    private String workDirBase;

    @Value("${drama.video.painted.template-dir:}")
    private String templateDirConfig;

    @Value("${drama.video.painted.scene-template:scripts/painted_scene_template.js}")
    private String sceneTemplateConfig;

    private final ExecutorService executor = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "painted-render");
        t.setDaemon(true);
        return t;
    });

    @Override
    public String name() {
        return "painted";
    }

    @Override
    public String submit(Shot shot, int seconds) {
        try {
            Path baseDir = Paths.get(workDirBase).toAbsolutePath().normalize();
            Path workDir = baseDir.resolve("painted-" + UUID.randomUUID()).normalize();
            if (!workDir.startsWith(baseDir)) {
                throw new RuntimeException("workDir escaped base directory: " + workDir);
            }
            Files.createDirectories(workDir.getParent());

            Path templateDir = resolveTemplateDir();
            if (!Files.isDirectory(templateDir)) {
                throw new RuntimeException("template dir not found: " + templateDir);
            }

            copyTemplate(templateDir, workDir);

            Path sceneTemplate = resolveSceneTemplate();
            if (!Files.isRegularFile(sceneTemplate)) {
                throw new RuntimeException("scene template not found: " + sceneTemplate);
            }

            String title = buildTitle(shot);
            String escapedTitle = jsonEscape(title);
            String template = Files.readString(sceneTemplate, StandardCharsets.UTF_8);
            String sceneJs = template
                    .replace("__TITLE__", escapedTitle)
                    .replace("__DUR__", Integer.toString(seconds));

            Path scenesDir = workDir.resolve("src/scenes");
            Files.createDirectories(scenesDir);

            Path demoJs = scenesDir.resolve("demo.js");
            if (Files.exists(demoJs)) {
                try {
                    Files.move(demoJs, scenesDir.resolve("demo.js.bak"),
                            StandardCopyOption.REPLACE_EXISTING);
                } catch (IOException e) {
                    Files.deleteIfExists(demoJs);
                }
            }

            Files.writeString(scenesDir.resolve("shot.js"), sceneJs, StandardCharsets.UTF_8);

            patchConfigDuration(workDir.resolve("src/config.js"), seconds);

            String shortTitle = title.length() > 80 ? title.substring(0, 80) + "..." : title;
            log.info("[painted] submit workDir={} seconds={} title={}", workDir, seconds, shortTitle);

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
                detail = new String(Files.readAllBytes(failedFlag), StandardCharsets.UTF_8);
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

    private Path resolveTemplateDir() {
        String cfg = templateDirConfig == null ? "" : templateDirConfig.trim();
        Path p = cfg.isEmpty() ? Paths.get("") : Paths.get(cfg);
        if (!p.isAbsolute()) {
            p = Paths.get(System.getProperty("user.dir")).resolve(p);
        }
        return p.toAbsolutePath().normalize();
    }

    private Path resolveSceneTemplate() {
        Path p = Paths.get(sceneTemplateConfig);
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
        t = t.strip();
        return t.length() > 60 ? t.substring(0, 60) : t;
    }

    private String jsonEscape(String s) {
        try {
            return MAPPER.writeValueAsString(s);
        } catch (Exception e) {
            return "\"\"";
        }
    }

    private void patchConfigDuration(Path configJs, int seconds) throws IOException {
        String content = Files.readString(configJs, StandardCharsets.UTF_8);
        String patched = content.replaceAll("(?m)^(\\s*duration\\s*:\\s*)\\d+",
                "$1" + seconds);
        if (patched.equals(content)) {
            throw new IOException("config.js 中未找到 duration 字段");
        }
        Files.writeString(configJs, patched, StandardCharsets.UTF_8);
    }

    private void runRender(Path workDir, int seconds) {
        Path outDir = workDir.resolve("out");
        try {
            Files.createDirectories(outDir);
            List<String> cmd = new ArrayList<>();
            cmd.add("node");
            cmd.add("render.mjs");
            cmd.add("--clip");
            cmd.add("--fps=12");
            cmd.add("--soft-gl");
            cmd.add("--out=out/video.mp4");
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.directory(workDir.toFile());
            pb.redirectErrorStream(true);
            Process proc = pb.start();
            boolean done = proc.waitFor(RENDER_TIMEOUT_MINUTES, TimeUnit.MINUTES);
            if (!done) {
                proc.destroyForcibly();
                Files.writeString(outDir.resolve("FAILED"), "渲染超时",
                        StandardCharsets.UTF_8);
                return;
            }
            if (proc.exitValue() != 0 || !Files.exists(outDir.resolve("video.mp4"))) {
                Files.writeString(outDir.resolve("FAILED"),
                        "渲染进程异常退出，exit=" + proc.exitValue(), StandardCharsets.UTF_8);
            }
        } catch (Exception e) {
            try {
                Files.writeString(outDir.resolve("FAILED"),
                        "渲染异常: " + e.getMessage(), StandardCharsets.UTF_8);
            } catch (IOException ignored) {
            }
            log.warn("[painted] render failed: {}", e.getMessage());
        }
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdownNow();
    }

    private void copyTemplate(Path src, Path dst) throws IOException {
    Files.createDirectories(dst);
    Files.walk(src).forEach(path -> {
        try {
            Path target = dst.resolve(src.relativize(path).toString());
            if (Files.isDirectory(path)) {
                Files.createDirectories(target);
            } else {
                String rel = src.relativize(path).toString().replace('\\', '/');
                if (rel.startsWith("node_modules/")) {
                    try {
                        Files.createSymbolicLink(target, path.toAbsolutePath());
                    } catch (Exception e) {
                        Files.copy(path, target, StandardCopyOption.REPLACE_EXISTING);
                    }
                } else {
                    Files.createDirectories(target.getParent());
                    Files.copy(path, target, StandardCopyOption.REPLACE_EXISTING);
                }
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    });
}

@Override
public ConnectivityResult probeConnectivity() {
    String templateDir = templateDirConfig;
    if (templateDir == null || templateDir.trim().isEmpty()) {
        return new ConnectivityResult(ConnectivityStatus.UNREACHABLE, "模板缺失");
    }
    Path renderScript = Paths.get(templateDir).resolve("render.mjs");
    if (!Files.exists(renderScript)) {
        return new ConnectivityResult(ConnectivityStatus.UNREACHABLE, "模板缺失");
    }
    return new ConnectivityResult(ConnectivityStatus.OK, "模板就绪");
}
}
