package com.dramafactory.repository;

import com.dramafactory.model.Episode;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface EpisodeRepository extends JpaRepository<Episode, Long> {

    List<Episode> findByProjectIdOrderByEpisodeNoAsc(Long projectId);

    long countByProjectId(Long projectId);

    /**
     * 按归属用户聚合统计剧集数（替代 N+1 逐项目 count）。
     */
    @org.springframework.data.jpa.repository.Query(
            "SELECT COUNT(e) FROM Episode e WHERE e.project.ownerId = :ownerId")
    long countByOwner(@org.springframework.data.repository.query.Param("ownerId") String ownerId);
}
