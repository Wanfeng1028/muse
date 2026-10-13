package com.dramafactory.repository;

import com.dramafactory.model.FinalCut;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * 成片数据访问层。
 * 提供按剧集维度查询成片记录的能力。
 */
public interface FinalCutRepository extends JpaRepository<FinalCut, Long> {

    /**
     * 根据剧集 ID 查询该剧集下的所有成片记录，按主键倒序（最新的在前）。
     *
     * @param episodeId 剧集 ID
     * @return 成片记录列表
     */
    List<FinalCut> findByEpisodeIdOrderByIdDesc(Long episodeId);

    /**
     * 查询指定剧集下最新的一条成片记录。
     *
     * @param episodeId 剧集 ID
     * @return 最新成片记录（可能为空）
     */
    Optional<FinalCut> findFirstByEpisodeIdOrderByIdDesc(Long episodeId);
}
