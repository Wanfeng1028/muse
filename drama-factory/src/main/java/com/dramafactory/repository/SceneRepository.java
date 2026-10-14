package com.dramafactory.repository;

import com.dramafactory.model.Scene;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SceneRepository extends JpaRepository<Scene, Long> {

    List<Scene> findByEpisodeIdOrderBySceneNoAsc(Long episodeId);

    long countByEpisodeId(Long episodeId);

    void deleteByEpisodeId(Long episodeId);

    /**
     * 按归属用户聚合统计场景数（场景→剧集→项目两级导航，替代 N+1）。
     */
    @org.springframework.data.jpa.repository.Query(
            "SELECT COUNT(s) FROM Scene s WHERE s.episode.project.ownerId = :ownerId")
    long countByOwner(@org.springframework.data.repository.query.Param("ownerId") String ownerId);
}
