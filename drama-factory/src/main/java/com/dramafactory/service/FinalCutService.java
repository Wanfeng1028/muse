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
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

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
     * 构造器注入所有依赖。
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

            // 第一步：拼接片段
            Path concatOut = finalsDir.resolve(base + "_concat.mp4");
            withFfmpegRetry("concat", () -> {
                ffmpegService.concatClips(clips, concatOut);
                return null;
            });

            // 第二步：生成字幕并烧录
            Path srt = subtitleService.buildSrt(episodeId, shots);
            Path finalOut = finalsDir.resolve(base + ".mp4");
            withFfmpegRetry("burn-subtitles", () -> {
                ffmpegService.burnSubtitles(concatOut, srt, finalOut);
                return null;
            });

            // 第三步：探测成片时长
            double dur = withFfmpegRetry("probe-duration", () -> ffmpegService.probeDurationSeconds(finalOut));

            // 更新成片记录为完成状态
            fc.setStatus(FinalCutStatus.READY);
            fc.setFilePath(finalOut.toString());
            fc.setDurationSeconds(dur);
            fc = finalCutRepository.save(fc);

            return toResponse(fc);
        } catch (Exception e) {
            // 失败时记录错误信息并置为失败状态
            fc.setStatus(FinalCutStatus.FAILED);
            fc.setErrorMessage(e.getMessage());
            finalCutRepository.save(fc);
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
     */
    private <T> T withFfmpegRetry(String operation, FfmpegStep<T> step) {
        int maxAttempts = Math.max(1, ffmpegRetryAttempts);
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                T result = step.run();
                if (attempt > 1) {
                    dramaMetrics.recordFfmpegRetry(operation, true, true);
                }
                return result;
            } catch (FfmpegService.FfmpegException e) {
                dramaMetrics.recordFfmpegRetry(operation, e.isTransient(), false);
                if (!e.isTransient() || attempt >= maxAttempts) {
                    throw e;
                }
                long backoffMs = ffmpegRetryBackoffMs * attempt;
                log.warn("ffmpeg step '{}' failed (attempt {}/{}), retrying in {}ms: {}",
                        operation, attempt, maxAttempts, backoffMs, e.getMessage());
                try {
                    Thread.sleep(backoffMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new FfmpegService.FfmpegException(
                            "ffmpeg retry interrupted: " + operation, true);
                }
            } catch (RuntimeException e) {
                throw e;
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }
        throw new IllegalStateException("unreachable: ffmpeg retry loop exhausted for " + operation);
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
