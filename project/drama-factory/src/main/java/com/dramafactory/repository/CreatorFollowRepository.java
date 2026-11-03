package com.dramafactory.repository;

import com.dramafactory.model.CreatorFollow;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * 创作者关注关系数据访问仓库接口，提供对关注关系的持久化操作
 */
public interface CreatorFollowRepository extends JpaRepository<CreatorFollow, Long> {

    /**
     * 根据创作者 ID 和关注者 ID 查询特定的关注关系
     *
     * @param creatorId 创作者 ID
     * @param followerId 关注者 ID
     * @return 匹配的关注关系，可能为空
     */
    Optional<CreatorFollow> findByCreatorIdAndFollowerId(Long creatorId, String followerId);

    /**
     * 统计指定创作者的关注者数量
     *
     * @param creatorId 创作者 ID
     * @return 该创作者的关注者总数
     */
    long countByCreatorId(Long creatorId);

    /**
     * 判断指定关注者是否已关注该创作者
     *
     * @param creatorId 创作者 ID
     * @param followerId 关注者 ID
     * @return 已关注返回 true，否则返回 false
     */
    boolean existsByCreatorIdAndFollowerId(Long creatorId, String followerId);

    /**
     * 查询指定关注者的全部关注记录
     *
     * @param followerId 关注者 ID
     * @return 该关注者的关注关系列表
     */
    List<CreatorFollow> findByFollowerId(String followerId);
}
