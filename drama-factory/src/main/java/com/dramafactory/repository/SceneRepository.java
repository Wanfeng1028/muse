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
}
