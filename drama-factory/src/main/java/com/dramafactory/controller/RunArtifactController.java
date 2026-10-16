package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.Scene;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.RunService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

/**
 * 运行产物 API：汇总一次 Run 下所有剧集的脚本、分镜、视频任务与成片。
 */
@RestController
@RequestMapping("/api/runs")
@Tag(name = "RunArtifacts", description = "查询一次运行下的全部产物")
public class RunArtifactController {

    private final RunService runService;
    private final EpisodeRepository episodeRepository;
    private final SceneRepository sceneRepository;
    private final ShotRepository shotRepository;
    private final VideoTaskRepository videoTaskRepository;
    private final FinalCutRepository finalCutRepository;

    public RunArtifactController(RunService runService,
                                 EpisodeRepository episodeRepository,
                                 SceneRepository sceneRepository,
                                 ShotRepository shotRepository,
                                 VideoTaskRepository videoTaskRepository,
                                 FinalCutRepository finalCutRepository) {
        this.runService = runService;
        this.episodeRepository = episodeRepository;
        this.sceneRepository = sceneRepository;
        this.shotRepository = shotRepository;
        this.videoTaskRepository = videoTaskRepository;
        this.finalCutRepository = finalCutRepository;
    }

    /**
     * 查询指定 Run 的所有产物。
     *
     * @param id Run ID
     * @return 产物响应
     */
    @GetMapping("/{id}/artifacts")
    @Transactional(readOnly = true)
    @Operation(summary = "查询运行的全部产物")
    public Records.RunArtifactsResponse artifacts(@Parameter(description = "Run ID") @PathVariable("id") Long id) {

        Records.RunDetailResponse run;
        try {
            run = runService.getRun(id);
        } catch (ResourceNotFoundException ex) {
            throw new ResourceNotFoundException("Run", id);
        }
        Long projectId = run.projectId();
        List<Episode> episodes = episodeRepository.findByProjectIdOrderByEpisodeNoAsc(projectId);

        List<Records.EpisodeArtifacts> episodeArtifacts = new ArrayList<>();
        for (Episode episode : episodes) {
            episodeArtifacts.add(buildEpisodeArtifacts(episode));
        }
        return new Records.RunArtifactsResponse(id, episodeArtifacts);
    }

    /**
     * 组装单个剧集的产物。
     *
     * @param episode 剧集实体
     * @return 剧集产物
     */
    private Records.EpisodeArtifacts buildEpisodeArtifacts(Episode episode) {
        Long episodeId = episode.getId();
        return new Records.EpisodeArtifacts(
                episodeId,
                episode.getEpisodeNo(),
                episode.getTitle(),
                buildScriptText(episodeId),
                buildShots(episodeId),
                buildVideos(episodeId),
                buildFinalCuts(episodeId)
        );
    }

    /**
     * 拼装剧集脚本文本：格式为「【第X场·地点】描述\n台词：对白」，多场以换行分隔。
     *
     * @param episodeId 剧集 ID
     * @return 脚本文本
     */
    private String buildScriptText(Long episodeId) {
        List<Scene> scenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episodeId);
        StringBuilder sb = new StringBuilder();
        for (Scene scene : scenes) {
            if (sb.length() > 0) {
                sb.append('\n');
            }
            sb.append("【第").append(scene.getSceneNo()).append("场·")
                    .append(scene.getLocation() == null ? "" : scene.getLocation()).append("】")
                    .append(scene.getDescription() == null ? "" : scene.getDescription());
            if (scene.getDialogue() != null && !scene.getDialogue().isBlank()) {
                sb.append('\n').append("台词：").append(scene.getDialogue());
            }
        }
        return sb.toString();
    }

    /**
     * 组装分镜列表。
     *
     * @param episodeId 剧集 ID
     * @return 分镜产物列表
     */
    private List<Records.ShotArtifact> buildShots(Long episodeId) {
        List<Shot> shots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
        List<Records.ShotArtifact> result = new ArrayList<>(shots.size());
        for (Shot shot : shots) {
            result.add(new Records.ShotArtifact(
                    shot.getId(),
                    shot.getShotNo(),
                    shot.getShotSize() == null ? null : String.valueOf(shot.getShotSize()),
                    shot.getCameraMove() == null ? null : String.valueOf(shot.getCameraMove()),
                    shot.getDescription(),
                    shot.getDurationSeconds()
            ));
        }
        return result;
    }

    /**
     * 组装视频任务列表。
     *
     * @param episodeId 剧集 ID
     * @return 视频任务产物列表
     */
    private List<Records.VideoArtifact> buildVideos(Long episodeId) {
        List<VideoTask> tasks = videoTaskRepository.findByEpisodeId(episodeId);
        tasks.sort(java.util.Comparator.comparing(VideoTask::getId));
        List<Records.VideoArtifact> result = new ArrayList<>(tasks.size());
        for (VideoTask task : tasks) {
            String status = task.getStatus() == null ? null : String.valueOf(task.getStatus());
            result.add(new Records.VideoArtifact(
                    task.getId(),
                    task.getShot().getId(),
                    task.getProvider(),
                    task.getModelUsed(),
                    status,
                    status,
                    "/media/videos/" + task.getId(),
                    task.getCostCents()
            ));
        }
        return result;
    }

    /**
     * 组装成片列表。
     *
     * @param episodeId 剧集 ID
     * @return 成片产物列表
     */
    private List<Records.FinalCutArtifact> buildFinalCuts(Long episodeId) {
        List<FinalCut> finalCuts = finalCutRepository.findByEpisodeIdOrderByIdDesc(episodeId);
        List<Records.FinalCutArtifact> result = new ArrayList<>(finalCuts.size());
        for (FinalCut cut : finalCuts) {
            result.add(new Records.FinalCutArtifact(
                    cut.getId(),
                    cut.getFilePath(),
                    "/media/finals/" + cut.getId(),
                    cut.getStatus() == null ? null : String.valueOf(cut.getStatus()),
                    cut.getQcStatus(),
                    cut.getQcNote(),
                    cut.getDurationSeconds()
            ));
        }
        return result;
    }
}
