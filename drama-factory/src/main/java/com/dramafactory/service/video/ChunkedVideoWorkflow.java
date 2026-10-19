package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.FfmpegService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 分段视频生成工作流（H3-Continuum 工作流思想的 API 版实现）。
 *
 * <p>流程：按 Shot 拆 chunk → 逐段 submit/poll → 单段可重试 → 下载片段 → ffmpeg 拼装。
 *
 * <p>与 H3-Continuum 自部署版的对应关系：
 * <ul>
 *   <li>chunk = 一个 Shot（时长 4–15 秒，与 H3 单 clip 对齐）</li>
 *   <li>review/重试 = {@link #retryChunk}，只重跑失败或不满意的那一段</li>
 *   <li>拼装 = {@link FfmpegService#concatClips}（API 版无 latent 连续性，靠首帧图+提示词衔接）</li>
 * </ul>
 */
@Service
public class ChunkedVideoWorkflow {

    private static final Logger log = LoggerFactory.getLogger(ChunkedVideoWorkflow.class);

    /**
     * 单个 chunk 的执行结果。
     *
     * @param index          分段序号（从 0 开始）
     * @param shotId         对应的 Shot ID
     * @param providerName   实际使用的提供方
     * @param providerTaskId 提供方任务 ID
     * @param videoUrl       完成后的视频地址
     * @param status         最终状态
     * @param errorMessage   失败原因
     */
    public record ChunkResult(int index, Long shotId, String providerName,
                              String providerTaskId, String videoUrl,
                              VideoProvider.RemoteStatus status, String errorMessage) {
        public boolean succeeded() {
            return status == VideoProvider.RemoteStatus.COMPLETED && videoUrl != null;
        }
    }

    private final VideoProviderRouter router;
    private final FfmpegService ffmpegService;
    private final long pollIntervalMs;
    private final long pollTimeoutMs;
    private final HttpClient downloadClient;

    @Autowired
    public ChunkedVideoWorkflow(
            VideoProviderRouter router,
            FfmpegService ffmpegService,
            @Value("${drama.video.chunk.poll-interval-ms:15000}") long pollIntervalMs,
            @Value("${drama.video.chunk.poll-timeout-ms:600000}") long pollTimeoutMs) {
        this.router = router;
        this.ffmpegService = ffmpegService;
        this.pollIntervalMs = pollIntervalMs;
        this.pollTimeoutMs = pollTimeoutMs;
        this.downloadClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    /**
     * 执行分段生成：提交所有 chunk 并轮询到全部完成/失败。
     *
     * @param shots        分镜列表（按顺序）
     * @param providerName 指定提供方（如 "minimax"）；为 null 时走 Router 默认链路
     * @param secondsPerChunk 每段目标时长（秒，会被各 provider 自行 clamp）
     * @return 每段的结果（按 shots 顺序）
     */
    public List<ChunkResult> run(List<Shot> shots, String providerName, int secondsPerChunk) {
        if (shots == null || shots.isEmpty()) {
            return List.of();
        }
        List<ChunkResult> results = new ArrayList<>();
        for (int i = 0; i < shots.size(); i++) {
            Shot shot = shots.get(i);
            results.add(submitAndWait(i, shot, providerName, secondsPerChunk));
        }
        return Collections.unmodifiableList(results);
    }

    /**
     * 重试单个 chunk（review 不通过或失败时调用）。
     *
     * @param index        分段序号
     * @param shot         对应的分镜
     * @param providerName 指定提供方；为 null 时走 Router 默认链路
     * @param secondsPerChunk 每段目标时长
     * @return 该段的新结果
     */
    public ChunkResult retryChunk(int index, Shot shot, String providerName, int secondsPerChunk) {
        log.info("分段工作流：第 {} 段重试", index);
        return submitAndWait(index, shot, providerName, secondsPerChunk);
    }

    /**
     * 下载所有成功的 chunk 并拼装成完整视频。
     *
     * @param results  run/retryChunk 返回的结果列表
     * @param workDir  工作目录（下载的片段放这里）
     * @param output   最终输出文件
     * @return 输出文件路径
     * @throws IllegalStateException 有 chunk 未成功时
     */
    public Path assemble(List<ChunkResult> results, Path workDir, Path output) {
        List<ChunkResult> failed = results.stream()
                .filter(r -> !r.succeeded())
                .toList();
        if (!failed.isEmpty()) {
            throw new IllegalStateException("有 " + failed.size()
                    + " 个分段未成功，无法拼装（先用 retryChunk 重试）");
        }
        try {
            Files.createDirectories(workDir);
        } catch (Exception e) {
            throw new RuntimeException("创建工作目录失败: " + workDir, e);
        }

        List<Path> clips = new ArrayList<>();
        for (ChunkResult r : results) {
            Path clipPath = workDir.resolve("chunk-%02d.mp4".formatted(r.index()));
            download(r.videoUrl(), clipPath);
            clips.add(clipPath);
        }
        ffmpegService.concatClips(clips, output);
        log.info("分段工作流：{} 个片段已拼装为 {}", clips.size(), output);
        return output;
    }

    // ---------- 内部实现 ----------

    private ChunkResult submitAndWait(int index, Shot shot, String providerName, int seconds) {
        VideoProvider provider;
        String resolvedName;
        if (providerName != null && !providerName.isBlank()) {
            provider = router.providerFor(providerName);
            resolvedName = providerName;
        } else {
            VideoProviderRouter.RouteResult route = router.submit(shot, seconds);
            provider = router.providerFor(route.providerName());
            resolvedName = route.providerName();
            return waitForCompletion(index, shot.getId(), resolvedName, provider,
                    route.providerTaskId());
        }

        String taskId;
        try {
            taskId = provider.submit(shot, seconds);
        } catch (Exception e) {
            log.warn("分段工作流：第 {} 段提交失败：{}", index, e.getMessage());
            return new ChunkResult(index, shot.getId(), resolvedName, null, null,
                    VideoProvider.RemoteStatus.FAILED, "提交失败: " + e.getMessage());
        }
        return waitForCompletion(index, shot.getId(), resolvedName, provider, taskId);
    }

    private ChunkResult waitForCompletion(int index, Long shotId, String providerName,
                                          VideoProvider provider, String taskId) {
        long deadline = System.currentTimeMillis() + pollTimeoutMs;
        while (System.currentTimeMillis() < deadline) {
            VideoProvider.ProbeResult probe;
            try {
                probe = provider.poll(taskId);
            } catch (Exception e) {
                log.warn("分段工作流：第 {} 段轮询异常：{}", index, e.getMessage());
                sleepQuietly(pollIntervalMs);
                continue;
            }
            if (probe.status() == VideoProvider.RemoteStatus.COMPLETED) {
                log.info("分段工作流：第 {} 段完成", index);
                return new ChunkResult(index, shotId, providerName, taskId,
                        probe.videoUrl(), probe.status(), null);
            }
            if (probe.status() == VideoProvider.RemoteStatus.FAILED) {
                log.warn("分段工作流：第 {} 段失败：{}", index, probe.errorMessage());
                return new ChunkResult(index, shotId, providerName, taskId, null,
                        probe.status(), probe.errorMessage());
            }
            sleepQuietly(pollIntervalMs);
        }
        log.warn("分段工作流：第 {} 段轮询超时", index);
        return new ChunkResult(index, shotId, providerName, taskId, null,
                VideoProvider.RemoteStatus.FAILED, "轮询超时（超过 " + pollTimeoutMs + "ms）");
    }

    private void download(String videoUrl, Path target) {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(videoUrl))
                    .timeout(Duration.ofMinutes(5))
                    .GET()
                    .build();
            HttpResponse<InputStream> response = downloadClient.send(request,
                    HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new RuntimeException("下载片段失败，状态码: " + response.statusCode());
            }
            try (InputStream in = response.body()) {
                Files.copy(in, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("下载视频片段失败: " + videoUrl, e);
        }
    }

    private static void sleepQuietly(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("分段工作流等待被中断", e);
        }
    }
}
