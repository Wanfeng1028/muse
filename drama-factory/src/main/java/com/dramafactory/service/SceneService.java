package com.dramafactory.service;

import com.dramafactory.dto.Records.SceneRequest;
import com.dramafactory.dto.Records.SceneResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Scene;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 场景服务：负责剧集下场景的增删改查。
 */
@Service
public class SceneService {

    private final SceneRepository sceneRepository;
    private final EpisodeRepository episodeRepository;

    // 构造器注入
    public SceneService(SceneRepository sceneRepository, EpisodeRepository episodeRepository) {
        this.sceneRepository = sceneRepository;
        this.episodeRepository = episodeRepository;
    }

    /** 在指定剧集下创建场景 */
    @Transactional
    public SceneResponse create(Long episodeId, SceneRequest request) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));
        Scene scene = new Scene();
        scene.setEpisode(episode);
        scene.setSceneNo(request.sceneNo());
        scene.setLocation(request.location());
        scene.setTimeOfDay(request.timeOfDay());
        scene.setDescription(request.description());
        scene.setDialogue(request.dialogue());
        scene.setPrompt(request.prompt());
        Scene saved = sceneRepository.save(scene);
        return toResponse(saved);
    }

    /** 查询指定剧集下的全部场景（按 sceneNo 升序） */
    @Transactional(readOnly = true)
    public List<SceneResponse> listByEpisode(Long episodeId) {
        return sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episodeId).stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    /** 更新场景 */
    @Transactional
    public SceneResponse update(Long id, SceneRequest request) {
        Scene scene = sceneRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Scene", id));
        scene.setSceneNo(request.sceneNo());
        scene.setLocation(request.location());
        scene.setTimeOfDay(request.timeOfDay());
        scene.setDescription(request.description());
        scene.setDialogue(request.dialogue());
        scene.setPrompt(request.prompt());
        Scene saved = sceneRepository.save(scene);
        return toResponse(saved);
    }

    /** 删除场景 */
    @Transactional
    public void delete(Long id) {
        if (!sceneRepository.existsById(id)) {
            throw new ResourceNotFoundException("Scene", id);
        }
        sceneRepository.deleteById(id);
    }

    /** 实体转 DTO */
    private SceneResponse toResponse(Scene scene) {
        return new SceneResponse(
                scene.getId(),
                scene.getEpisode().getId(),
                scene.getSceneNo(),
                scene.getLocation(),
                scene.getTimeOfDay(),
                scene.getDescription(),
                scene.getDialogue(),
                scene.getPrompt(),
                scene.getCreatedAt(),
                scene.getUpdatedAt()
        );
    }
}
