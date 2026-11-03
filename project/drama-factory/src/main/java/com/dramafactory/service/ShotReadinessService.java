package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 分镜视频生成准备度检查服务
 */
@Service
public class ShotReadinessService {

    private final ShotRepository shotRepository;
    private final VideoTaskRepository videoTaskRepository;

    public ShotReadinessService(ShotRepository shotRepository, VideoTaskRepository videoTaskRepository) {
        this.shotRepository = shotRepository;
        this.videoTaskRepository = videoTaskRepository;
    }

    /**
     * 准备度检查项
     */
    public record ReadinessCheck(String key, String level, boolean ok, String message) {
    }

    /**
     * 分镜准备度报告
     */
    public record ShotReadinessReport(Long shotId, Integer shotNo, boolean ready, List<ReadinessCheck> checks, String promptPreview, boolean promptPreviewDerived) {
    }

    /**
     * 评估单个分镜的视频生成准备度
     */
    public ShotReadinessReport assess(Shot shot) {
        String description = shot.getDescription();
        String videoPrompt = shot.getVideoPrompt();
        Integer durationSeconds = shot.getDurationSeconds();

        // 1. description 检查
        boolean descOk = description != null && !description.trim().isEmpty();
        ReadinessCheck descCheck = new ReadinessCheck("description", "BLOCKING", descOk, descOk ? "描述已填写" : "描述为空");

        // 2. videoPrompt 检查
        boolean promptOk = videoPrompt != null && !videoPrompt.isEmpty();
        ReadinessCheck promptCheck = new ReadinessCheck("videoPrompt", "BLOCKING", promptOk, promptOk ? "视频提示词已填写" : "视频提示词为空");

        // 3. duration 检查
        boolean durationOk = durationSeconds != null && durationSeconds > 0;
        ReadinessCheck durationCheck = new ReadinessCheck("duration", "BLOCKING", durationOk, durationOk ? "时长已设置" : "时长未设置或无效");

        // 4. shotSize 检查
        boolean shotSizeOk = shot.getShotSize() != null;
        ReadinessCheck shotSizeCheck = new ReadinessCheck("shotSize", "WARNING", shotSizeOk, shotSizeOk ? "景别已指定" : "景别未指定");

        // 5. cameraMove 检查
        boolean cameraMoveOk = shot.getCameraMove() != null;
        ReadinessCheck cameraMoveCheck = new ReadinessCheck("cameraMove", "WARNING", cameraMoveOk, cameraMoveOk ? "运镜已指定" : "运镜未指定");

        // 6. dialogueAudio 检查
        boolean dialogueAudioOk = !(Boolean.TRUE.equals(shot.getGenerateAudio()) && (shot.getDialogue() == null || shot.getDialogue().isEmpty()));
        ReadinessCheck dialogueAudioCheck = new ReadinessCheck("dialogueAudio", "BLOCKING", dialogueAudioOk, dialogueAudioOk ? "音频生成条件满足" : "需生成音频但对话为空");

        // 7. activeTask 检查
        java.util.Optional<VideoTask> activeTaskOpt = videoTaskRepository.findFirstByShotIdAndStatusInOrderByIdAsc(shot.getId(), List.of(VideoTaskStatus.PENDING, VideoTaskStatus.PROCESSING));
        boolean activeTaskOk = activeTaskOpt.isEmpty();
        String activeTaskMsg = activeTaskOk ? "无进行中视频任务" : "已有进行中视频任务：" + activeTaskOpt.get().getStatus().name();
        ReadinessCheck activeTaskCheck = new ReadinessCheck("activeTask", "INFO", activeTaskOk, activeTaskMsg);

        List<ReadinessCheck> checks = List.of(descCheck, promptCheck, durationCheck, shotSizeCheck, cameraMoveCheck, dialogueAudioCheck, activeTaskCheck);

        // ready 仅由 BLOCKING 项决定
        boolean ready = checks.stream()
                .filter(c -> "BLOCKING".equals(c.level()))
                .allMatch(ReadinessCheck::ok);

        // promptPreview 与 promptPreviewDerived 拼接逻辑
        String promptPreview;
        boolean promptPreviewDerived;

        if (videoPrompt != null && !videoPrompt.isEmpty()) {
            promptPreview = videoPrompt;
            promptPreviewDerived = false;
        } else {
            promptPreviewDerived = true;
            if (description == null || description.trim().isEmpty()) {
                promptPreview = "";
            } else {
                promptPreview = "画面：" + description +
                        "；景别：" + (shot.getShotSize() == null ? "未指定" : shot.getShotSize().name()) +
                        "；运镜：" + (shot.getCameraMove() == null ? "未指定" : shot.getCameraMove().name()) +
                        "；时长：" + (durationSeconds == null ? "未指定" : durationSeconds + "秒");
            }
        }

        return new ShotReadinessReport(shot.getId(), shot.getShotNo(), ready, checks, promptPreview, promptPreviewDerived);
    }

    /**
     * 获取单个分镜的准备度报告
     */
    public ShotReadinessReport getForShot(Long episodeId, Long shotId) {
        Shot shot = shotRepository.findById(shotId).orElseThrow(() -> ResourceNotFoundException.withKey("shot", String.valueOf(shotId)));
        if (shot.getEpisode() == null || !shot.getEpisode().getId().equals(episodeId)) {
            throw ResourceNotFoundException.withKey("shot", String.valueOf(shotId));
        }
        return assess(shot);
    }

    /**
     * 评估整集分镜的视频生成准备度
     */
    public List<ShotReadinessReport> assessEpisode(Long episodeId) {
        List<Shot> shots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
        return shots.stream().map(this::assess).toList();
    }
}
