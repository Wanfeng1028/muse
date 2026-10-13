package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

/**
 * 剧集状态自动流转服务。
 *
 * <p>状态机：DRAFT → SCRIPTED → GENERATED → REVIEWED，只能前进不能后退；
 * 但质检打回时允许 GENERATED / REVIEWED → SCRIPTED（返工重拍）。</p>
 */
@Service
public class EpisodeStatusFlowService {

    private static final Logger log = LoggerFactory.getLogger(EpisodeStatusFlowService.class);

    private final EpisodeRepository episodeRepository;
    private final ShotRepository shotRepository;
    private final VideoTaskRepository videoTaskRepository;

    public EpisodeStatusFlowService(EpisodeRepository episodeRepository,
                                    ShotRepository shotRepository,
                                    VideoTaskRepository videoTaskRepository) {
        this.episodeRepository = episodeRepository;
        this.shotRepository = shotRepository;
        this.videoTaskRepository = videoTaskRepository;
    }

    /**
     * 当某个视频任务完成后刷新剧集状态。
     *
     * <p>检查剧集下所有分镜的最新任务是否全部为 DONE，若是则将剧集状态推进到 GENERATED。
     * 为避免覆盖人工质检结论，仅允许从 DRAFT 或 SCRIPTED 推进；已是 GENERATED 或 REVIEWED 时保持不动。</p>
     *
     * @param episodeId 剧集 ID
     */
    @Transactional
    public void refreshAfterTaskDone(Long episodeId) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));

        List<Shot> shots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
        if (shots.isEmpty()) {
            // 没有分镜，无需推进
            return;
        }

        // 逐个检查每个分镜的最新任务是否均已完成
        for (Shot shot : shots) {
            Optional<VideoTask> latestTask = videoTaskRepository.findFirstByShotIdOrderByIdDesc(shot.getId());
            if (latestTask.isEmpty() || latestTask.get().getStatus() != VideoTaskStatus.DONE) {
                // 存在未完成的分镜任务，剧集尚不能推进
                return;
            }
        }

        // 所有分镜的最新任务均已 DONE，尝试推进状态
        EpisodeStatus current = episode.getStatus();
        if (current == EpisodeStatus.DRAFT || current == EpisodeStatus.SCRIPTED) {
            episode.setStatus(EpisodeStatus.GENERATED);
            episodeRepository.save(episode);
            log.info("剧集状态自动推进：episodeId={}, {} -> GENERATED", episodeId, current);
        } else {
            // 已是 GENERATED / REVIEWED，避免覆盖人工质检结论
            log.debug("剧集 {} 当前状态为 {}，跳过自动推进", episodeId, current);
        }
    }

    /**
     * 质检通过：直接将剧集状态置为 REVIEWED。
     *
     * @param episodeId 剧集 ID
     */
    @Transactional
    public void markQcApproved(Long episodeId) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));

        EpisodeStatus previous = episode.getStatus();
        episode.setStatus(EpisodeStatus.REVIEWED);
        episodeRepository.save(episode);
        log.info("剧集质检通过：episodeId={}, {} -> REVIEWED", episodeId, previous);
    }

    /**
     * 质检打回：将剧集状态置回 SCRIPTED，进入返工重拍流程。
     *
     * @param episodeId 剧集 ID
     * @param reason    打回原因
     */
    @Transactional
    public void markQcRejected(Long episodeId, String reason) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));

        EpisodeStatus previous = episode.getStatus();
        episode.setStatus(EpisodeStatus.SCRIPTED);
        episodeRepository.save(episode);
        log.info("剧集质检打回：episodeId={}, {} -> SCRIPTED, reason={}", episodeId, previous, reason);
    }
}
