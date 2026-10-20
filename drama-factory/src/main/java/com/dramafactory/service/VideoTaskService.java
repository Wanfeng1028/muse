package com.dramafactory.service;

import com.dramafactory.billing.CostLedgerEntry;
import com.dramafactory.billing.CostLedgerService;
import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.VideoProvider.ProbeResult;
import com.dramafactory.service.video.RateLimitedException;
import com.dramafactory.service.video.VideoProvider;
import com.dramafactory.service.video.VideoProviderRouter;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationContext;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 视频生成任务状态机服务。
 * 状态流转：PENDING -> PROCESSING -> DONE / FAILED。
 * 采用指数退避重试，超时或限流由统一异常处理逻辑接管。
 */
@Service
public class VideoTaskService {

    private static final Logger log = LoggerFactory.getLogger(VideoTaskService.class);

    private final VideoTaskRepository videoTaskRepository;
    private final ShotRepository shotRepository;
    private final FfmpegService ffmpegService;
    private final ApplicationContext applicationContext;
    private final EpisodeStatusFlowService episodeStatusFlowService;

    private final Environment environment;
    private final VideoProviderRouter videoProviderRouter;
    private final String providerName;
    private final long pollIntervalMs;
    private final int maxAttempts;
    private final String storageDir;
    private final DramaMetrics dramaMetrics;

    /** 成本账本服务，可为 null（测试/未装配时跳过结算） */
    private final CostLedgerService costLedgerService;

    /** 轮询方法是否正在执行中，用于关闭时等待在途任务收尾。 */
    private final AtomicBoolean pollInFlight = new AtomicBoolean(false);

    public VideoTaskService(VideoTaskRepository videoTaskRepository,
                            ShotRepository shotRepository,
                            FfmpegService ffmpegService,
                            ApplicationContext applicationContext,
                            EpisodeStatusFlowService episodeStatusFlowService,
                            Environment environment,
                            VideoProviderRouter videoProviderRouter,
                            @Value("${drama.video.provider:mock}") String providerName,
                            @Value("${drama.video.poll-interval-ms:10000}") long pollIntervalMs,
                            @Value("${drama.video.max-attempts:8}") int maxAttempts,
                            @Value("${drama.storage:./data/media}") String storageDir,
                            DramaMetrics dramaMetrics) {
        this(videoTaskRepository, shotRepository, ffmpegService, applicationContext, episodeStatusFlowService,
                environment, videoProviderRouter, providerName, pollIntervalMs, maxAttempts, storageDir,
                dramaMetrics, null);
    }

    @org.springframework.beans.factory.annotation.Autowired
    public VideoTaskService(VideoTaskRepository videoTaskRepository,
                            ShotRepository shotRepository,
                            FfmpegService ffmpegService,
                            ApplicationContext applicationContext,
                            EpisodeStatusFlowService episodeStatusFlowService,
                            Environment environment,
                            VideoProviderRouter videoProviderRouter,
                            @Value("${drama.video.provider:mock}") String providerName,
                            @Value("${drama.video.poll-interval-ms:10000}") long pollIntervalMs,
                            @Value("${drama.video.max-attempts:8}") int maxAttempts,
                            @Value("${drama.storage:./data/media}") String storageDir,
                            DramaMetrics dramaMetrics,
                            CostLedgerService costLedgerService) {
        this.videoTaskRepository = videoTaskRepository;
        this.shotRepository = shotRepository;
        this.ffmpegService = ffmpegService;
        this.applicationContext = applicationContext;
        this.episodeStatusFlowService = episodeStatusFlowService;
        this.environment = environment;
        this.videoProviderRouter = videoProviderRouter;
        this.providerName = providerName;
        this.pollIntervalMs = pollIntervalMs;
        this.maxAttempts = maxAttempts;
        this.storageDir = storageDir;
        this.dramaMetrics = dramaMetrics;
        this.costLedgerService = costLedgerService;
    }

    /**
     * 根据 providerName 从容器中获取对应的视频提供者。
     */
    /**
     * 根据 providerName 从容器中获取对应的视频提供者。
     * 通道名优先读运行时 Environment（settings.json 可即时覆盖），回退构造器注入的默认值；环境变量优先级最高。
     */


    /**
     * 为指定镜头提交一个视频生成任务。
     * 幂等语义：若该镜头已存在 PENDING / PROCESSING 的进行中任务，则直接返回该任务且 created=false；
     * 否则新建任务并返回 created=true。
     * 并发限制说明：本实现为 check-then-insert，单实例部署下可接受；极端并发下存在竞态，
     * 未加数据库层唯一约束或悲观锁，如需强一致请补充相应 DB 约束。
     */
    @Transactional
    public Records.SubmitOutcome submit(Long shotId) {
        var existing = videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(
                shotId, List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING));
        if (existing.isPresent()) {
            return new Records.SubmitOutcome(toResponse(existing.get()), false);
        }
        Shot shot = shotRepository.findById(shotId)
                .orElseThrow(() -> new ResourceNotFoundException("Shot", shotId));
        VideoTask task = new VideoTask();
        task.setShot(shot);
        task.setProvider(providerName);
        task.setStatus(VideoTaskStatus.PENDING);
        task.setAttempts(0);
        task.setNextRetryAt(LocalDateTime.now());
        return new Records.SubmitOutcome(toResponse(videoTaskRepository.save(task)), true);
    }

    /**
     * 为某剧集下的所有镜头批量提交视频任务。
     */
    @Transactional
    public List<Records.VideoTaskResponse> submitAllForEpisode(Long episodeId) {
        List<Shot> shots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
        List<Records.VideoTaskResponse> result = new ArrayList<>();
        for (Shot shot : shots) {
            result.add(submit(shot.getId()).task());
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
        if (!pollInFlight.compareAndSet(false, true)) {
            log.debug("video task poll already in flight, skipping this trigger");
            dramaMetrics.recordPollSkipped();
            return;
        }
        MDC.put("request_id", "poll-" + UUID.randomUUID().toString().substring(0, 8));
        try {
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
                } catch (FfmpegService.FfmpegInterruptedException ie) {
                    // v2.32：中断走终止路径——恢复中断标志，标记永久失败，不重排
                    Thread.currentThread().interrupt();
                    failOrRetry(task, ie.getMessage(), true);
                } catch (Exception e) {
                    boolean permanent = e instanceof FfmpegService.FfmpegException fe && !fe.isTransient();
                    failOrRetry(task, e.getMessage(), permanent);
                }
                videoTaskRepository.save(task);
            });
        } finally {
            MDC.clear();
            pollInFlight.set(false);
        }
    }

    /**
     * 应用关闭收尾钩子：等待在途的一轮 processDueTasks 执行完毕，最多等待 25 秒。
     * 轮询单轮上限处理 20 个任务，mock provider 下远小于此时限；超时后不再等待直接返回，
     * 由外层调度器的 await-termination 做最终兜底。
     * 真实 agnes provider 下单个任务可能耗时较长，超时熔断是后续 DoD 轮次事项，此处如实注明。
     */
    @PreDestroy
    public void awaitPollCompletion() {
        if (!pollInFlight.get()) {
            log.info("关闭收尾：无在途轮询任务，直接返回");
            return;
        }
        log.info("关闭收尾：检测到在途轮询任务，开始等待其收尾（最多 25 秒）");
        long deadline = System.currentTimeMillis() + 25_000L;
        while (pollInFlight.get() && System.currentTimeMillis() < deadline) {
            try {
                Thread.sleep(200L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                log.warn("关闭收尾：等待在途轮询任务时被中断，提前返回");
                return;
            }
        }
        if (pollInFlight.get()) {
            log.warn("关闭收尾：等待在途轮询任务超时（25 秒），不再等待直接返回，交由调度器 await-termination 兜底");
        } else {
            log.info("关闭收尾：在途轮询任务已完成");
        }
    }

    /**
     * 提交任务到视频提供者，进入 PROCESSING 状态。
     */
    private void doSubmit(VideoTask task) {
        Integer durationSeconds = task.getShot().getDurationSeconds();
        int seconds = durationSeconds != null ? durationSeconds : 5;
        VideoProviderRouter.RouteResult result = videoProviderRouter.submit(task.getShot(), seconds);
        log.info("视频任务已提交：taskId={}，shotId={}，provider={}，providerTaskId={}", task.getId(), task.getShot().getId(), result.providerName(), result.providerTaskId());
        if (result.fallbackReason() != null) {
            log.warn("视频任务降级提交：taskId={}，原因={}", task.getId(), result.fallbackReason());
            task.setFallbackReason(result.fallbackReason());
        }
        task.setProvider(result.providerName());
        task.setProviderTaskId(result.providerTaskId());
        task.setLedgerEntryId(result.ledgerEntryId());
        task.setStatus(VideoTaskStatus.PROCESSING);
        task.setNextRetryAt(LocalDateTime.now().plusNanos((pollIntervalMs) * 1_000_000L));
    }

    /**
     * 轮询提供者任务状态。
     */
    private void doPoll(VideoTask task) throws Exception {
        String providerNameForPoll = task.getProvider() != null ? task.getProvider() : "mock";
        ProbeResult result = videoProviderRouter.providerFor(providerNameForPoll).poll(task.getProviderTaskId());
        switch (result.status()) {
            case COMPLETED -> {
                log.info("视频任务完成：taskId={}，shotId={}", task.getId(), task.getShot().getId());
                settleLedgerComplete(task);
                downloadVideo(task, result.videoUrl());
            }
            case FAILED -> {
                log.warn("视频任务提供方返回失败：taskId={}，shotId={}，原因={}", task.getId(), task.getShot().getId(), result.errorMessage());
                settleLedgerFail(task, result.errorMessage());
                failOrRetry(task, result.errorMessage(), false);
            }
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

        if (url != null && url.startsWith("file://")) {
            Path src = Paths.get(URI.create(url));
            Files.copy(src, out, StandardCopyOption.REPLACE_EXISTING);
        } else if (url != null && url.startsWith("mock://")) {
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

        // 视频任务完成：尝试推进剧集状态（全部镜头 DONE → GENERATED）
        try {
            Long episodeId = task.getShot().getEpisode().getId();
            episodeStatusFlowService.refreshAfterTaskDone(episodeId);
        } catch (Exception e) {
            log.warn("刷新剧集状态失败（不影响任务完成）: {}", e.getMessage());
        }
    }

    /**
     * 账本结算（提供方成功）：RESERVED → COMPLETED，实际费用按提交时的估算值结算。
     * 结算后把任务上的条目 id 置空，保证幂等；任何异常只记日志，不影响主流程。
     */
    private void settleLedgerComplete(VideoTask task) {
        Long entryId = task.getLedgerEntryId();
        if (entryId == null || costLedgerService == null) {
            return;
        }
        try {
            CostLedgerEntry entry = costLedgerService.requireEntry(entryId);
            costLedgerService.complete(entryId, entry.getEstimatedUsd(), durationMsOf(task));
            task.setLedgerEntryId(null);
        } catch (RuntimeException e) {
            log.warn("账本结算（完成）失败，不影响主流程：taskId={}，entryId={}，原因={}",
                    task.getId(), entryId, e.getMessage());
        }
    }

    /**
     * 账本结算（提供方失败）：RESERVED → FAILED，实际费用记 0。
     * 结算后把任务上的条目 id 置空，保证幂等；任何异常只记日志，不影响主流程。
     */
    private void settleLedgerFail(VideoTask task, String reason) {
        Long entryId = task.getLedgerEntryId();
        if (entryId == null || costLedgerService == null) {
            return;
        }
        try {
            String note = "提供方任务失败：" + (reason == null ? "" : reason);
            costLedgerService.fail(entryId, 0d, durationMsOf(task), note);
            task.setLedgerEntryId(null);
        } catch (RuntimeException e) {
            log.warn("账本结算（失败）失败，不影响主流程：taskId={}，entryId={}，原因={}",
                    task.getId(), entryId, e.getMessage());
        }
    }

    /**
     * 任务从创建到现在的耗时毫秒数，异常时返回 0。
     */
    private long durationMsOf(VideoTask task) {
        try {
            if (task.getCreatedAt() == null) {
                return 0L;
            }
            long ms = Duration.between(task.getCreatedAt(), LocalDateTime.now()).toMillis();
            return Math.max(ms, 0L);
        } catch (RuntimeException e) {
            return 0L;
        }
    }

    /**
     * 失败处理：累计尝试次数，超过上限标记 FAILED，否则按指数退避安排下次重试。
     */
    private void failOrRetry(VideoTask task, String err, boolean permanent) {
        if (permanent) {
            task.setAttempts(task.getAttempts() + 1);
            task.setStatus(VideoTaskStatus.FAILED);
            task.setErrorMessage("[永久失败，不再重试] " + err);
            task.setNextRetryAt(LocalDateTime.now());
            log.warn("视频任务永久失败，不再重试：taskId={}，shotId={}，错误={}", task.getId(), task.getShot().getId(), err);
            return;
        }
        task.setAttempts(task.getAttempts() + 1);
        task.setErrorMessage(err);
        if (task.getAttempts() >= maxAttempts) {
            task.setStatus(VideoTaskStatus.FAILED);
            log.warn("视频任务达到最大重试次数，标记失败：taskId={}，shotId={}，最后错误={}", task.getId(), task.getShot().getId(), err);
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
                t.getUpdatedAt(),
                t.getFallbackReason()
        );
    }
}
