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

    private final FinalCutRepository finalCutRepository;
    private final EpisodeRepository episodeRepository;
    private final ShotRepository shotRepository;
    private final VideoTaskRepository videoTaskRepository;
    private final SubtitleService subtitleService;
    private final FfmpegService ffmpegService;
    private final String storageDir;

    /**
     * 构造器注入所有依赖。
     */
    public FinalCutService(FinalCutRepository finalCutRepository,
                           EpisodeRepository episodeRepository,
                           ShotRepository shotRepository,
                           VideoTaskRepository videoTaskRepository,
                           SubtitleService subtitleService,
                           FfmpegService ffmpegService,
                           @Value("${drama.storage:./data/media}") String storageDir) {
        this.finalCutRepository = finalCutRepository;
        this.episodeRepository = episodeRepository;
        this.shotRepository = shotRepository;
        this.videoTaskRepository = videoTaskRepository;
        this.subtitleService = subtitleService;
        this.ffmpegService = ffmpegService;
        this.storageDir = storageDir;
    }

    /**
     * 为指定剧集构建成片：拼接分镜片段 + 烧录字幕 → H.264 mp4。
     * 构建过程若失败，会将成片状态置为 FAILED 并记录错误信息后抛出异常。
     */
    @Transactional
    public Records.FinalCutResponse buildFinalCut(Long episodeId) {
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
            ffmpegService.concatClips(clips, concatOut);

            // 第二步：生成字幕并烧录
            Path srt = subtitleService.buildSrt(episodeId, shots);
            Path finalOut = finalsDir.resolve(base + ".mp4");
            ffmpegService.burnSubtitles(concatOut, srt, finalOut);

            // 第三步：探测成片时长
            double dur = ffmpegService.probeDurationSeconds(finalOut);

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
                fc.getCreatedAt(),
                fc.getUpdatedAt()
        );
    }
}
