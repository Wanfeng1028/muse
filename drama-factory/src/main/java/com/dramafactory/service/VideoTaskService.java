package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.VideoProvider.ProbeResult;
import com.dramafactory.service.video.RateLimitedException;
import com.dramafactory.service.video.VideoProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationContext;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * 视频生成任务状态机服务。
 * 状态流转：PENDING -> PROCESSING -> DONE / FAILED。
 * 采用指数退避重试，超时或限流由统一异常处理逻辑接管。
 */
@Service
public class VideoTaskService {

    private final VideoTaskRepository videoTaskRepository;
    private final ShotRepository shotRepository;
    private final FfmpegService ffmpegService;
    private final ApplicationContext applicationContext;

    private final String providerName;
    private final long pollIntervalMs;
    private final int maxAttempts;
    private final String storageDir;

    public VideoTaskService(VideoTaskRepository videoTaskRepository,
                            ShotRepository shotRepository,
                            FfmpegService ffmpegService,
                            ApplicationContext applicationContext,
                            @Value("${drama.video.provider:mock}") String providerName,
                            @Value("${drama.video.poll-interval-ms:10000}") long pollIntervalMs,
                            @Value("${drama.video.max-attempts:8}") int maxAttempts,
                            @Value("${drama.storage:./data/media}") String storageDir) {
        this.videoTaskRepository = videoTaskRepository;
        this.shotRepository = shotRepository;
        this.ffmpegService = ffmpegService;
        this.applicationContext = applicationContext;
        this.providerName = providerName;
        this.pollIntervalMs = pollIntervalMs;
        this.maxAttempts = maxAttempts;
        this.storageDir = storageDir;
    }

    /**
     * 根据 providerName 从容器中获取对应的视频提供者。
     */
    private VideoProvider provider() {
        if ("agnes".equals(providerName)) {
            return applicationContext.getBean("agnesVideoProvider", VideoProvider.class);
        }
        return applicationContext.getBean("mockVideoProvider", VideoProvider.class);
    }

    /**
     * 为指定镜头提交一个视频生成任务。
     */
    @Transactional
    public Records.VideoTaskResponse submit(Long shotId) {
        Shot shot = shotRepository.findById(shotId)
                .orElseThrow(() -> new ResourceNotFoundException("Shot", shotId));
        VideoTask task = new VideoTask();
        task.setShot(shot);
        task.setProvider(providerName);
        task.setStatus(VideoTaskStatus.PENDING);
        task.setAttempts(0);
        task.setNextRetryAt(LocalDateTime.now());
        return toResponse(videoTaskRepository.save(task));
    }

    /**
     * 为某剧集下的所有镜头批量提交视频任务。
     */
    @Transactional
    public List<Records.VideoTaskResponse> submitAllForEpisode(Long episodeId) {
        List<Shot> shots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
        List<Records.VideoTaskResponse> result = new ArrayList<>();
        for (Shot shot : shots) {
            result.add(submit(shot.getId()));
        }
        return result;
    }

    /**
     * 重试失败的任务：仅 FAILED 状态允许重试。
     */
    @Transactional
    public Records.VideoTaskResponse retry(Long taskId) {
        VideoTask task = videoTaskRepository.findById(taskId)
                .orElseThrow(() -> new ResourceNotFoundException("VideoTask", taskId));
        if (task.getStatus() != VideoTaskStatus.FAILED) {
            throw new IllegalStateException("只有 FAILED 状态的任务才能重试");
        }
        task.setStatus(VideoTaskStatus.PENDING);
        task.setAttempts(0);
        task.setNextRetryAt(LocalDateTime.now());
        task.setErrorMessage(null);
        return toResponse(videoTaskRepository.save(task));
    }

    /**
     * 查询指定镜头下的所有视频任务。
     */
    @Transactional(readOnly = true)
    public List<Records.VideoTaskResponse> listByShot(Long shotId) {
        List<VideoTask> tasks = videoTaskRepository.findByShotIdOrderByIdDesc(shotId);
        List<Records.VideoTaskResponse> result = new ArrayList<>();
        for (VideoTask task : tasks) {
            result.add(toResponse(task));
        }
        return result;
    }

    /**
     * 按 ID 获取单个任务详情。
     */
    @Transactional(readOnly = true)
    public Records.VideoTaskResponse get(Long id) {
        VideoTask task = videoTaskRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("VideoTask", id));
        return toResponse(task);
    }

    /**
     * 定时轮询到期任务。每次最多处理 20 个。
     * 异常在此层统一处理：限流走 RateLimitedException 分支，其余走 failOrRetry。
     */
    @Scheduled(fixedDelayString = "${drama.video.poll-interval-ms:10000}")
    @Transactional
    public void processDueTasks() {
        LocalDateTime now = LocalDateTime.now();
        List<VideoTask> due = videoTaskRepository
                .findByStatusInAndNextRetryAtLessThanEqualOrderByIdAsc(
                        List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING), now);

        due.stream().limit(20).forEach(task -> {
            try {
                if (task.getStatus() == VideoTaskStatus.PENDING) {
                    doSubmit(task);
                } else {
                    doPoll(task);
                }
            } catch (RateLimitedException e) {
                task.setNextRetryAt(now.plusSeconds(Math.max(e.getRetryAfterSeconds(), 30)));
            } catch (Exception e) {
                failOrRetry(task, e.getMessage());
            }
            videoTaskRepository.save(task);
        });
    }

    /**
     * 提交任务到视频提供者，进入 PROCESSING 状态。
     */
    private void doSubmit(VideoTask task) {
        Integer durationSeconds = task.getShot().getDurationSeconds();
        int seconds = durationSeconds != null ? durationSeconds : 5;
        String providerTaskId = provider().submit(task.getShot(), seconds);
        task.setProviderTaskId(providerTaskId);
        task.setStatus(VideoTaskStatus.PROCESSING);
        task.setNextRetryAt(LocalDateTime.now().plusNanos((pollIntervalMs) * 1_000_000L));
    }

    /**
     * 轮询提供者任务状态。
     */
    private void doPoll(VideoTask task) throws Exception {
        ProbeResult result = provider().poll(task.getProviderTaskId());
        switch (result.status()) {
            case COMPLETED -> downloadVideo(task, result.videoUrl());
            case FAILED -> failOrRetry(task, result.errorMessage());
            case QUEUED, PROCESSING -> task.setNextRetryAt(LocalDateTime.now().plusNanos((pollIntervalMs) * 1_000_000L));
        }
    }

    /**
     * 下载或生成视频文件到本地存储。
     * mock:// 协议走 ffmpeg 生成测试片段，其余走 HTTP 下载。
     */
    private void downloadVideo(VideoTask task, String url) throws Exception {
        Path dir = Paths.get(storageDir, "videos");
        Files.createDirectories(dir);
        Path out = dir.resolve("task_" + task.getId() + ".mp4");

        if (url != null && url.startsWith("mock://")) {
            int seconds = 5;
            int idx = url.indexOf("seconds=");
            if (idx >= 0) {
                String s = url.substring(idx + "seconds=".length());
                int amp = s.indexOf('&');
                if (amp >= 0) {
                    s = s.substring(0, amp);
                }
                try {
                    seconds = Integer.parseInt(s.trim());
                } catch (NumberFormatException ignored) {
                    seconds = 5;
                }
            }
            ffmpegService.generateTestClip(out, seconds);
        } else {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(URI.create(url)).GET().build();
            client.send(request, HttpResponse.BodyHandlers.ofFile(out));
        }

        task.setLocalPath(out.toString());
        task.setVideoUrl(url);
        task.setStatus(VideoTaskStatus.DONE);
    }

    /**
     * 失败处理：累计尝试次数，超过上限标记 FAILED，否则按指数退避安排下次重试。
     */
    private void failOrRetry(VideoTask task, String err) {
        task.setAttempts(task.getAttempts() + 1);
        task.setErrorMessage(err);
        if (task.getAttempts() >= maxAttempts) {
            task.setStatus(VideoTaskStatus.FAILED);
        }
        task.setNextRetryAt(LocalDateTime.now().plusNanos(computeBackoffMs(task.getAttempts()) * 1_000_000L));
    }

    /**
     * 指数退避：base = 10s，倍数 2^attempts，封顶 10 分钟。
     * 保持静态纯函数，便于单元测试。
     */
    static long computeBackoffMs(int attempts) {
        return Math.min(10_000L * (1L << Math.min(attempts, 6)), 600_000L);
    }

    /**
     * 实体到 DTO 的映射。
     */
    private Records.VideoTaskResponse toResponse(VideoTask t) {
        return new Records.VideoTaskResponse(
                t.getId(),
                t.getShot().getId(),
                t.getProvider(),
                t.getProviderTaskId(),
                t.getStatus(),
                t.getStatus().getLabel(),
                t.getAttempts(),
                t.getVideoUrl(),
                t.getLocalPath() != null && Files.exists(Paths.get(t.getLocalPath())),
                t.getErrorMessage(),
                t.getNextRetryAt(),
                t.getCreatedAt(),
                t.getUpdatedAt()
        );
    }
}
