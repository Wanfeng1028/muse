package com.dramafactory.repository;

import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

/**
 * 资产库数据访问层。
 */
public interface AssetRepository extends JpaRepository<Asset, Long> {

    /** 按类型查询 */
    List<Asset> findByType(AssetType type);

    /** 按来源查询 */
    List<Asset> findBySource(AssetSource source);

    /** 按 Run id 查询 */
    List<Asset> findByRunId(Long runId);

    /** 组合条件搜索：类型/来源/关键词（文件名或标签模糊匹配），按创建时间倒序 */
    @Query("SELECT a FROM Asset a WHERE (:type IS NULL OR a.type = :type) " +
           "AND (:source IS NULL OR a.source = :source) " +
           "AND (:keyword IS NULL OR a.fileName LIKE %:keyword% OR a.tags LIKE %:keyword%) " +
           "ORDER BY a.createdAt DESC")
    List<Asset> search(@Param("type") AssetType type,
                       @Param("source") AssetSource source,
                       @Param("keyword") String keyword);
}
