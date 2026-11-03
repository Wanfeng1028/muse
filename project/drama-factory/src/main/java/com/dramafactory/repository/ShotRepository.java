package com.dramafactory.repository;

import com.dramafactory.model.Shot;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * 镜头数据访问层。
 */
public interface ShotRepository extends JpaRepository<Shot, Long> {

    /**
     * 根据剧集 ID 查询镜头列表，按镜头序号升序排列。
     *
     * @param episodeId 剧集 ID
     * @return 镜头列表
     */
    List<Shot> findByEpisodeIdOrderByShotNoAsc(Long episodeId);

    /**
     * 统计指定剧集下的镜头数量。
     *
     * @param episodeId 剧集 ID
     * @return 镜头数量
     */
    long countByEpisodeId(Long episodeId);
}
