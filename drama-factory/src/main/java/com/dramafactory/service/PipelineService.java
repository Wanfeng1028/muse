package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.VideoTask;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;

/**
 * 生产看板聚合服务：项目 → 剧集 → 分镜 → 视频任务 → 成片。
 */
@Service
public class PipelineService {

    private final DramaProjectRepository dramaProjectRepository;
    private final EpisodeRepository episodeRepository;
    private final ShotRepository shotRepository;
    private final VideoTaskRepository videoTaskRepository;
    private final FinalCutRepository finalCutRepository;

    /** 构造器注入所有依赖仓库。 */
    public PipelineService(DramaProjectRepository dramaProjectRepository,
                           EpisodeRepository episodeRepository,
                           ShotRepository shotRepository,
                           VideoTaskRepository videoTaskRepository,
                           FinalCutRepository finalCutRepository) {
        this.dramaProjectRepository = dramaProjectRepository;
        this.episodeRepository = episodeRepository;
        this.shotRepository = shotRepository;
        this.videoTaskRepository = videoTaskRepository;
        this.finalCutRepository = finalCutRepository;
    }

    /**
     * 获取单个项目的生产看板聚合视图。
     *
     * @param projectId 项目 ID
     * @return 项目维度的聚合视图
     */
    @Transactional(readOnly = true)
    public Records.PipelineProjectView getProjectPipeline(Long projectId) {
        // 查询项目，不存在则抛出异常
        DramaProject project = dramaProjectRepository.findById(projectId)
                .orElseThrow(() -> new ResourceNotFoundException("DramaProject", projectId));

        // 按剧集编号升序获取该项目下所有剧集
        List<Episode> episodes = episodeRepository.findByProjectIdOrderByEpisodeNoAsc(projectId);

        // 逐个剧集组装聚合视图
        List<Records.PipelineEpisodeView> episodeViews = new ArrayList<>();
        for (Episode episode : episodes) {
            episodeViews.add(buildEpisodeView(episode));
        }

        return new Records.PipelineProjectView(project.getId(), project.getTitle(), episodeViews);
    }

    /**
     * 列出所有项目的生产看板聚合视图。
     *
     * @return 所有项目维度的聚合视图
     */
    @Transactional(readOnly = true)
    public List<Records.PipelineProjectView> listAllPipelines() {
        List<DramaProject> projects = dramaProjectRepository.findAll();
        List<Records.PipelineProjectView> result = new ArrayList<>();
        for (DramaProject project : projects) {
            result.add(getProjectPipeline(project.getId()));
        }
        return result;
    }

    /**
     * 组装单个剧集的聚合视图：统计分镜数量、各状态视频任务数量、最新成片状态。
     *
     * @param episode 剧集实体
     * @return 剧集维度的聚合视图
     */
    private Records.PipelineEpisodeView buildEpisodeView(Episode episode) {
        Long episodeId = episode.getId();

        // 统计分镜数量
        long shotCount = shotRepository.countByEpisodeId(episodeId);

        // 获取该剧集下所有视频任务并统计各状态数量
        List<VideoTask> tasks = videoTaskRepository.findByEpisodeId(episodeId);
        long pendingTasks = 0L;
        long processingTasks = 0L;
        long doneTasks = 0L;
        long failedTasks = 0L;
        for (VideoTask task : tasks) {
            if (task.getStatus() == null) {
                continue;
            }
            switch (task.getStatus()) {
                case PENDING -> pendingTasks++;
                case PROCESSING -> processingTasks++;
                case DONE -> doneTasks++;
                case FAILED -> failedTasks++;
                default -> {
                    // 其他状态不计入统计
                }
            }
        }

        // 查询该剧集最新的成片状态，不存在则为 NONE
        String finalCutStatus = finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(episodeId)
                .map(f -> f.getStatus().name())
                .orElse("NONE");

        return new Records.PipelineEpisodeView(
                episodeId,
                episode.getEpisodeNo(),
                episode.getTitle(),
                episode.getStatus() == null ? null : episode.getStatus().name(),
                shotCount,
                pendingTasks,
                processingTasks,
                doneTasks,
                failedTasks,
                finalCutStatus
        );
    }
}
