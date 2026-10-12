package com.dramafactory.service;

import com.dramafactory.dto.Records.EpisodeRequest;
import com.dramafactory.dto.Records.EpisodeResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 剧集业务服务：负责剧集的增删改查。
 */
@Service
public class EpisodeService {

    private final EpisodeRepository episodeRepository;
    private final DramaProjectRepository projectRepository;
    private final SceneRepository sceneRepository;

    public EpisodeService(EpisodeRepository episodeRepository,
                          DramaProjectRepository projectRepository,
                          SceneRepository sceneRepository) {
        this.episodeRepository = episodeRepository;
        this.projectRepository = projectRepository;
        this.sceneRepository = sceneRepository;
    }

    /** 在指定项目下创建剧集 */
    @Transactional
    public EpisodeResponse create(Long projectId, EpisodeRequest request) {
        if (!projectRepository.existsById(projectId)) {
            throw new ResourceNotFoundException("Project", projectId);
        }
        Episode episode = new Episode();
        episode.setProject(projectRepository.getReferenceById(projectId));
        episode.setEpisodeNo(request.episodeNo());
        episode.setTitle(request.title());
        episode.setOutline(request.outline());
        episode.setStatus(request.status() != null ? request.status() : EpisodeStatus.DRAFT);
        episode.setDurationSec(request.durationSec());
        Episode saved = episodeRepository.save(episode);
        return toResponse(saved);
    }

    /** 查询指定项目下的全部剧集，按集号升序 */
    @Transactional(readOnly = true)
    public List<EpisodeResponse> listByProject(Long projectId) {
        if (!projectRepository.existsById(projectId)) {
            throw new ResourceNotFoundException("Project", projectId);
        }
        return episodeRepository.findByProjectIdOrderByEpisodeNoAsc(projectId)
                .stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    /** 查询单个剧集 */
    @Transactional(readOnly = true)
    public EpisodeResponse get(Long id) {
        Episode episode = episodeRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", id));
        return toResponse(episode);
    }

    /** 更新剧集 */
    @Transactional
    public EpisodeResponse update(Long id, EpisodeRequest request) {
        Episode episode = episodeRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", id));
        episode.setEpisodeNo(request.episodeNo());
        episode.setTitle(request.title());
        episode.setOutline(request.outline());
        episode.setStatus(request.status() != null ? request.status() : episode.getStatus());
        episode.setDurationSec(request.durationSec());
        Episode saved = episodeRepository.save(episode);
        return toResponse(saved);
    }

    /** 删除剧集 */
    @Transactional
    public void delete(Long id) {
        Episode episode = episodeRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", id));
        episodeRepository.delete(episode);
    }

    /** 实体转 DTO，填充 projectId 与 sceneCount */
    private EpisodeResponse toResponse(Episode episode) {
        long sceneCount = sceneRepository.countByEpisodeId(episode.getId());
        return new EpisodeResponse(
                episode.getId(),
                episode.getProject() != null ? episode.getProject().getId() : null,
                episode.getEpisodeNo(),
                episode.getTitle(),
                episode.getOutline(),
                episode.getStatus(),
                episode.getDurationSec(),
                sceneCount,
                episode.getCreatedAt(),
                episode.getUpdatedAt()
        );
    }
}
