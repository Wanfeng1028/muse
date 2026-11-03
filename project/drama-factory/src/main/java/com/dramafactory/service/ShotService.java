package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 分镜服务：提供分镜的增删改查以及排序功能。
 */
@Service
public class ShotService {

    private final ShotRepository shotRepository;
    private final EpisodeRepository episodeRepository;

    /**
     * 构造器注入。
     */
    public ShotService(ShotRepository shotRepository, EpisodeRepository episodeRepository) {
        this.shotRepository = shotRepository;
        this.episodeRepository = episodeRepository;
    }

    /**
     * 在指定剧集下创建分镜。
     */
    @Transactional
    public Records.ShotResponse create(Long episodeId, Records.ShotRequest req) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));

        Shot shot = new Shot();
        shot.setEpisode(episode);
        shot.setShotNo(req.shotNo());
        shot.setShotSize(req.shotSize());
        shot.setCameraMove(req.cameraMove());
        shot.setDescription(req.description());
        shot.setDurationSeconds(req.durationSeconds());
        shot.setDialogue(req.dialogue());
        shot.setVideoPrompt(req.videoPrompt());

        Shot saved = shotRepository.save(shot);
        return toResponse(saved);
    }

    /**
     * 按分镜号升序查询指定剧集下的所有分镜。
     */
    @Transactional(readOnly = true)
    public List<Records.ShotResponse> listByEpisode(Long episodeId) {
        return shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId)
                .stream()
                .map(this::toResponse)
                .toList();
    }

    /**
     * 根据 id 查询分镜。
     */
    @Transactional(readOnly = true)
    public Records.ShotResponse get(Long id) {
        Shot shot = shotRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Shot", id));
        return toResponse(shot);
    }

    /**
     * 更新分镜全部字段。
     */
    @Transactional
    public Records.ShotResponse update(Long id, Records.ShotRequest req) {
        Shot shot = shotRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Shot", id));

        shot.setShotNo(req.shotNo());
        shot.setShotSize(req.shotSize());
        shot.setCameraMove(req.cameraMove());
        shot.setDescription(req.description());
        shot.setDurationSeconds(req.durationSeconds());
        shot.setDialogue(req.dialogue());
        shot.setVideoPrompt(req.videoPrompt());

        Shot saved = shotRepository.save(shot);
        return toResponse(saved);
    }

    /**
     * 删除分镜。
     */
    @Transactional
    public void delete(Long id) {
        if (!shotRepository.existsById(id)) {
            throw new ResourceNotFoundException("Shot", id);
        }
        shotRepository.deleteById(id);
    }

    /**
     * 按传入的 id 列表顺序重排分镜号（1..n）。
     * 每个分镜必须属于指定剧集，否则抛出 IllegalArgumentException。
     */
    @Transactional
    public void reorder(Long episodeId, List<Long> shotIds) {
        if (shotIds == null || shotIds.isEmpty()) {
            return;
        }

        List<Shot> shots = shotRepository.findAllById(shotIds);
        if (shots.size() != shotIds.size()) {
            throw new IllegalArgumentException("存在无效的分镜 id");
        }

        // 建立 id -> Shot 的映射，便于按列表顺序更新
        java.util.Map<Long, Shot> shotMap = new java.util.HashMap<>();
        for (Shot shot : shots) {
            if (shot.getEpisode() == null || !episodeId.equals(shot.getEpisode().getId())) {
                throw new IllegalArgumentException("分镜 " + shot.getId() + " 不属于剧集 " + episodeId);
            }
            shotMap.put(shot.getId(), shot);
        }

        int order = 1;
        for (Long shotId : shotIds) {
            Shot shot = shotMap.get(shotId);
            if (shot == null) {
                throw new IllegalArgumentException("存在无效的分镜 id: " + shotId);
            }
            shot.setShotNo(order);
            order++;
        }

        shotRepository.saveAll(shotMap.values());
    }

    /**
     * 实体 -> DTO 映射。
     */
    private Records.ShotResponse toResponse(Shot shot) {
        return new Records.ShotResponse(
                shot.getId(),
                shot.getEpisode() == null ? null : shot.getEpisode().getId(),
                shot.getShotNo(),
                shot.getShotSize(),
                shot.getShotSize() == null ? null : shot.getShotSize().getLabel(),
                shot.getCameraMove(),
                shot.getCameraMove() == null ? null : shot.getCameraMove().getLabel(),
                shot.getDescription(),
                shot.getDurationSeconds(),
                shot.getDialogue(),
                shot.getVideoPrompt(),
                shot.getCreatedAt(),
                shot.getUpdatedAt()
        );
    }
}
