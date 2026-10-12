package com.dramafactory.repository;

import com.dramafactory.model.Episode;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface EpisodeRepository extends JpaRepository<Episode, Long> {

    List<Episode> findByProjectIdOrderByEpisodeNoAsc(Long projectId);

    long countByProjectId(Long projectId);
}
