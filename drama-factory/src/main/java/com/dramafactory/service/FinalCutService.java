package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.metrics.DramaMetrics;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 剪辑成片服务：将分镜片段按序拼接，并烧录字幕生成 H.264 mp4 成片。
 */
@Service
public class FinalCutService {

    private static final Logger log = LoggerFactory.getLogger(FinalCutService.class);

    private final FinalCutRepository finalCutRepository;
    private final EpisodeRepository episodeRepository;
    private final ShotRepository shotRepository;
    private final VideoTaskRepository videoTaskRepository;
    private final SubtitleService subtitleService;
    private final FfmpegService ffmpegService;
    private final EpisodeStatusFlowService episodeStatusFlowService;
    private final String storageDir;
    /** v2.4 指标埋点：成片构建次数/耗时。 */
    private final DramaMetrics dramaMetrics;
    private final int ffmpegRetryAttempts;
    private final long ffmpegRetryBackoffMs;
    /**
     * v2.31：单次成片构建内所有 ffmpeg 步骤共享的退避预算（毫秒），总睡眠不超过该值。
     * 配置键 drama.ffmpeg.retry-total-budget-ms（环境变量 FFMPEG_RETRY_TOTAL_BUDGET_MS），默认 20000。
     */
    private final long ffmpegRetryTotalBudgetMs;

    private FinalCutService self;

    private VideoNormalizationService normalizationService;

    @Autowired
    public void setSelf(@Lazy FinalCutService self) {
        this.self = self;
    }

    /**
     * 规格统一服务（可选注入；单测直接 new 时为 null 则跳过规格统一，保持旧行为）。
     */
    @Autowired(required = false)
    public void setNormalizationService(VideoNormalizationService normalizationService) {
        this.normalizationService = normalizationService;
    }

    /**
     * 构造器注入所有依赖。
     * v2.31：退避预算未显式传入时委托到 13 参构造器，使用默认预算 20000L。
     */
    public FinalCutService(FinalCutRepository finalCutRepository,
                           EpisodeRepository episodeRepository,
                           ShotRepository shotRepository,
                           VideoTaskRepository videoTaskRepository,
                           SubtitleService subtitleService,
                           FfmpegService ffmpegService,
                           EpisodeStatusFlowService episodeStatusFlowService,
                           @Value("${drama.storage:./data/media}") String storageDir,
                           DramaMetrics dramaMetrics,
                           @Value("${drama.ffmpeg.retry-attempts:3}") int ffmpegRetryAttempts,
                           @Value("${drama.ffmpeg.retry-backoff-ms:2000}") long ffmpegRetryBackoffMs) {
        this(finalCutRepository, episodeRepository, shotRepository, videoTaskRepository,
                subtitleService, ffmpegService, episodeStatusFlowService, storageDir,
                dramaMetrics, ffmpegRetryAttempts, ffmpegRetryBackoffMs, 20000L);
    }

    /**
     * v2.31：构造器注入所有依赖，并显式指定单次成片构建共享的退避预算。
     */
    @Autowired
    public FinalCutService(FinalCutRepository finalCutRepository,
                           EpisodeRepository episodeRepository,
                           ShotRepository shotRepository,
                           VideoTaskRepository videoTaskRepository,
                           SubtitleService subtitleService,
                           FfmpegService ffmpegService,
                           EpisodeStatusFlowService episodeStatusFlowService,
                           @Value("${drama.storage:./data/media}") String storageDir,
                           DramaMetrics dramaMetrics,
                           @Value("${drama.ffmpeg.retry-attempts:3}") int ffmpegRetryAttempts,
                           @Value("${drama.ffmpeg.retry-backoff-ms:2000}") long ffmpegRetryBackoffMs,
                           @Value("${drama.ffmpeg.retry-total-budget-ms:20000}") long ffmpegRetryTotalBudgetMs) {
        this.finalCutRepository = finalCutRepository;
        this.episodeRepository = episodeRepository;
        this.shotRepository = shotRepository;
        this.videoTaskRepository = videoTaskRepository;
        this.subtitleService = subtitleService;
        this.ffmpegService = ffmpegService;
        this.episodeStatusFlowService = episodeStatusFlowService;
        this.storageDir = storageDir;
        this.dramaMetrics = dramaMetrics;
        this.ffmpegRetryAttempts = ffmpegRetryAttempts;
        this.ffmpegRetryBackoffMs = ffmpegRetryBackoffMs;
        this.ffmpegRetryTotalBudgetMs = ffmpegRetryTotalBudgetMs;
    }

    /**
     * 为指定剧集构建成片（指标 wrapper：记录构建次数与耗时）。
     * 事务边界在此方法上，内层 doBuildFinalCut 与其同事务。
     */
    @Transactional
    public Records.FinalCutResponse buildFinalCut(Long episodeId) {
        long start = System.currentTimeMillis();
        try {
            Records.FinalCutResponse resp = doBuildFinalCut(episodeId);
            dramaMetrics.recordFinalCutBuild(System.currentTimeMillis() - start, true);
            return resp;
        } catch (RuntimeException e) {
            dramaMetrics.recordFinalCutBuild(System.currentTimeMillis() - start, false);
            throw e;
        }
    }

    /**
     * 在独立事务中记录构建失败。若直接在外层事务里保存 FAILED 状态，
     * 外层事务因异常回滚时会把 FAILED 记录一并吞掉，导致失败无迹可查。
     * 用 REQUIRES_NEW 确保失败记录一定落盘。
     *
     * @param episodeId    剧集 ID（已提交，可见）
     * @param title        成片标题
     * @param errorMessage 错误信息
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordBuildFailure(Long episodeId, String title, String errorMessage) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));
        FinalCut fc = new FinalCut();
        fc.setEpisode(episode);
        fc.setTitle(title);
        fc.setStatus(FinalCutStatus.FAILED);
        fc.setErrorMessage(errorMessage);
        finalCutRepository.save(fc);
    }

    /**
     * 为指定剧集构建成片：拼接分镜片段 + 烧录字幕 → H.264 mp4。
     * 构建过程若失败，会将成片状态置为 FAILED 并记录错误信息后抛出异常。
     */
    private Records.FinalCutResponse doBuildFinalCut(Long episodeId) {
        // 校验剧集是否存在
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));

        // 新建成片记录，初始状态为构建中
        FinalCut fc = new FinalCut();
        fc.setEpisode(episode);
        fc.setTitle("第" + episode.getEpisodeNo() + "集成片");
        fc.setStatus(FinalCutStatus.BUILDING);
        fc = finalCutRepository.save(fc);

        try {
            // 获取该剧集下所有分镜，按分镜号升序
            List<Shot> shots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
            if (shots.isEmpty()) {
                throw new IllegalStateException("该剧集没有分镜");
            }

            // 收集每个分镜已完成的视频片段路径
            List<Path> clips = new ArrayList<>();
            for (Shot s : shots) {
                VideoTask t = videoTaskRepository.findFirstByShotIdOrderByIdDesc(s.getId())
                        .filter(x -> x.getStatus() == VideoTaskStatus.DONE
                                && x.getLocalPath() != null
                                && Files.exists(Paths.get(x.getLocalPath())))
                        .orElseThrow(() -> new IllegalStateException(
                                "分镜 " + s.getShotNo() + " 尚无已完成的视频"));
                clips.add(Paths.get(t.getLocalPath()));
            }

            // 准备输出目录
            Path finalsDir = Paths.get(storageDir, "finals");
            Files.createDirectories(finalsDir);

            String base = "episode_" + episodeId + "_final_" + System.currentTimeMillis();

            // v2.31：单次成片构建内所有 ffmpeg 步骤共享一份退避预算，总睡眠不超过预算。
            AtomicLong retryBudget = new AtomicLong(Math.max(0, ffmpegRetryTotalBudgetMs));

            // 新增：规格统一——各家模型输出的分辨率/帧率/编码各不相同，成片前统一到目标规格。
            // 放在拼接之前：concat demuxer 要求流参数一致，逐段先统一可避免混合拼接的音画问题；
            // 字幕仍在统一规格之后烧录，保证字样清晰。单段失败不污染整批，失败段汇总后报错。
            List<Path> uniformClips = clips;
            if (normalizationService != null && normalizationService.isEnabled()) {
                Path normDir = finalsDir.resolve(base + "_norm");
                List<VideoNormalizationService.SegmentReport> reports =
                        normalizationService.normalizeAll(clips, normDir);
                List<Path> okClips = new ArrayList<>();
                List<String> failedSegs = new ArrayList<>();
                for (VideoNormalizationService.SegmentReport r : reports) {
                    if (r.ok()) {
                        okClips.add(r.output());
                        if (r.upsampled()) {
                            log.warn("分镜片段已升采样（非原生 {}x{} → 目标规格）: {}",
                                    r.sourceWidth(), r.sourceHeight(), r.input().getFileName());
                        }
                    } else {
                        failedSegs.add(r.input().getFileName() + ": " + r.errorMessage());
                    }
                }
                if (!failedSegs.isEmpty()) {
                    throw new IllegalStateException("分镜规格统一失败: " + String.join("; ", failedSegs));
                }
                uniformClips = okClips;
            }

            // 第一步：拼接片段
            Path concatOut = finalsDir.resolve(base + "_concat.mp4");
            final List<Path> clipsToConcat = uniformClips;
            withFfmpegRetry("concat", () -> {
                ffmpegService.concatClips(clipsToConcat, concatOut);
                return null;
            }, retryBudget);

            // 第二步：生成字幕并烧录
            Path srt = subtitleService.buildSrt(episodeId, shots);
            Path finalOut = finalsDir.resolve(base + ".mp4");
            withFfmpegRetry("burn-subtitles", () -> {
                ffmpegService.burnSubtitles(concatOut, srt, finalOut);
                return null;
            }, retryBudget);

            // 第三步：探测成片时长
            double dur = withFfmpegRetry("probe-duration", () -> ffmpegService.probeDurationSeconds(finalOut), retryBudget);

            // 更新成片记录为完成状态
            fc.setStatus(FinalCutStatus.READY);
            fc.setFilePath(finalOut.toString());
            fc.setDurationSeconds(dur);
            fc = finalCutRepository.save(fc);

            return toResponse(fc);
        } catch (Exception e) {
            // 失败时在独立事务中记录 FAILED（外层事务回滚会吞掉直接 save）
            self.recordBuildFailure(episodeId, fc.getTitle(), e.getMessage());
            throw e instanceof RuntimeException re ? re : new RuntimeException(e);
        }
    }

    /**
     * ffmpeg 步骤抽象：允许以 lambda 形式传入单个 ffmpeg 调用。
     */
    private interface FfmpegStep<T> {
        T run() throws Exception;
    }

    /**
     * 对单个 ffmpeg 步骤执行有界重试：仅对可瞬时重试的失败（isTransient）重试，
     * 每次退避 ffmpegRetryBackoffMs * attempt 毫秒，最多 max(1, ffmpegRetryAttempts) 次。
     * v2.31：退避睡眠从 retryBudget 共享预算中认领，预算耗尽后仍继续尝试剩余次数但不再睡眠。
     */
    private <T> T withFfmpegRetry(String operation, FfmpegStep<T> step, AtomicLong retryBudget) {
        int maxAttempts = Math.max(1, ffmpegRetryAttempts);
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                T result = step.run();
                if (attempt > 1) {
                    dramaMetrics.recordFfmpegRetry(operation, true, true);
                }
                return result;
            } catch (FfmpegService.FfmpegInterruptedException ie) {
                // v2.32：中断信号直接终止重试循环，不睡眠、不重试、不记 transient 指标
                throw ie;
            } catch (FfmpegService.FfmpegException e) {
                dramaMetrics.recordFfmpegRetry(operation, e.isTransient(), false);
                if (!e.isTransient() || attempt >= maxAttempts) {
                    throw e;
                }
                long backoffMs = ffmpegRetryBackoffMs * attempt;
                long sleepMs = claimRetryBackoff(retryBudget, backoffMs);
                if (sleepMs > 0) {
                    log.warn("ffmpeg step '{}' failed (attempt {}/{}), retrying in {}ms: {}",
                            operation, attempt, maxAttempts, sleepMs, e.getMessage());
                    try {
                        Thread.sleep(sleepMs);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        throw new FfmpegService.FfmpegInterruptedException(
                                "ffmpeg retry interrupted: " + operation, ie);
                    }
                } else {
                    log.warn("ffmpeg step '{}' failed (attempt {}/{}), retrying without backoff (budget exhausted): {}",
                            operation, attempt, maxAttempts, e.getMessage());
                }
            } catch (RuntimeException e) {
                // v2.32 flaky-6：未知 RuntimeException 保守按瞬时失败处理。
                // 论证：FfmpegInterruptedException 已被上方专用 catch 拦截，到不了本分支；
                // 其余 RuntimeException 语义未知，与 FfmpegException 兼容构造器
                // "默认 transient=true，有界重试覆盖"的既有约定保持一致，
                // 包装为 transient FfmpegException 后走下方统一重试分支（记指标、退避、有界）。
                // 不改变 FfmpegException(transient=false) 的快速失败，也不改变普通 transient 的重试行为。
                FfmpegService.FfmpegException wrapped = new FfmpegService.FfmpegException(
                        "unknown runtime failure in ffmpeg step '" + operation + "': " + e.getMessage(), true);
                wrapped.initCause(e);
                dramaMetrics.recordFfmpegRetry(operation, true, false);
                if (attempt >= maxAttempts) {
                    throw wrapped;
                }
                long backoffMs = ffmpegRetryBackoffMs * attempt;
                long sleepMs = claimRetryBackoff(retryBudget, backoffMs);
                if (sleepMs > 0) {
                    log.warn("ffmpeg step '{}' failed (attempt {}/{}), retrying in {}ms: {}",
                            operation, attempt, maxAttempts, sleepMs, e.getMessage());
                    try {
                        Thread.sleep(sleepMs);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        throw new FfmpegService.FfmpegInterruptedException(
                                "ffmpeg retry interrupted: " + operation, ie);
                    }
                } else {
                    log.warn("ffmpeg step '{}' failed (attempt {}/{}), retrying without backoff (budget exhausted): {}",
                            operation, attempt, maxAttempts, e.getMessage());
                }
            } catch (Exception e) {
                // v2.32 flaky-6：理论路径，实际不可达。
                // 依据 B5 审计：三个调用点（concatClips/burnSubtitles 经 FfmpegService.run，
                // probeDurationSeconds 直接）的受检异常出口仅为 FfmpegException；
                // FfmpegStep.run() 声明的其它受检异常在现有 lambda 实现中不存在。
                // 保持现状，不引入无用的收敛代码。
                throw new RuntimeException(e);
            }
        }
        throw new IllegalStateException("unreachable: ffmpeg retry loop exhausted for " + operation);
    }

    /**
     * v2.31：从共享退避预算中认领睡眠毫秒数。
     *
     * @param retryBudget 本次构建共享的剩余预算（毫秒）
     * @param requestedMs 本次希望睡眠的毫秒数
     * @return 实际可睡眠的毫秒数（不超过剩余预算；预算耗尽、预算为 null 或请求非正时返回 0）
     */
    static long claimRetryBackoff(AtomicLong retryBudget, long requestedMs) {
        if (retryBudget == null || requestedMs <= 0) {
            return 0;
        }
        long remaining = retryBudget.get();
        if (remaining <= 0) {
            return 0;
        }
        long grant = Math.min(requestedMs, remaining);
        retryBudget.addAndGet(-grant);
        return grant;
    }

    /**
     * 查询指定剧集下的所有成片记录。
     */
    @Transactional(readOnly = true)
    public List<Records.FinalCutResponse> listByEpisode(Long episodeId) {
        return finalCutRepository.findByEpisodeIdOrderByIdDesc(episodeId).stream()
                .map(this::toResponse)
                .toList();
    }

    /**
     * 按 id 查询成片记录，查不到抛 ResourceNotFoundException。
     */
    @Transactional(readOnly = true)
    public Records.FinalCutResponse get(Long id) {
        FinalCut fc = finalCutRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("FinalCut", id));
        return toResponse(fc);
    }

    /**
     * 成片质检：通过 → 剧集 REVIEWED；打回 → 剧集回退到 SCRIPTED（返工重拍），打回原因记在成片上。
     * verdict 只能是 APPROVED 或 REJECTED。
     */
    @Transactional
    public Records.FinalCutResponse qc(Long id, Records.QcRequest req) {
        FinalCut fc = finalCutRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("FinalCut", id));
        if (fc.getStatus() != FinalCutStatus.READY) {
            throw new IllegalStateException("成片尚未完成，无法质检");
        }
        String verdict = req.verdict() == null ? "" : req.verdict().trim().toUpperCase();
        if (!"APPROVED".equals(verdict) && !"REJECTED".equals(verdict)) {
            throw new IllegalArgumentException("verdict 只能是 APPROVED 或 REJECTED");
        }
        fc.setQcStatus(verdict);
        fc.setQcNote(req.note());
        fc.setQcAt(java.time.LocalDateTime.now());
        finalCutRepository.save(fc);

        Long episodeId = fc.getEpisode().getId();
        if ("APPROVED".equals(verdict)) {
            episodeStatusFlowService.markQcApproved(episodeId);
        } else {
            episodeStatusFlowService.markQcRejected(episodeId, req.note());
        }
        return toResponse(fc);
    }

    /**
     * 实体 → DTO 映射。
     */
    private Records.FinalCutResponse toResponse(FinalCut fc) {
        String filePath = fc.getFilePath();
        String fileName = (filePath == null || filePath.isEmpty())
                ? null
                : Paths.get(filePath).getFileName().toString();
        return new Records.FinalCutResponse(
                fc.getId(),
                fc.getEpisode().getId(),
                fc.getTitle(),
                filePath,
                fileName,
                fc.getStatus(),
                fc.getStatus() == null ? null : fc.getStatus().getLabel(),
                fc.getDurationSeconds(),
                fc.getErrorMessage(),
                fc.getQcStatus(),
                fc.getQcNote(),
                fc.getQcAt(),
                fc.getCreatedAt(),
                fc.getUpdatedAt()
        );
    }
}
