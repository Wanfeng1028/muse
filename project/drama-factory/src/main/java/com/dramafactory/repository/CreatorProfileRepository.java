package com.dramafactory.repository;

import com.dramafactory.model.CreatorProfile;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * 创作者档案数据访问仓库接口，提供对创作者档案的持久化操作
 */
public interface CreatorProfileRepository extends JpaRepository<CreatorProfile, Long> {

    /**
     * 根据创作者的唯一标识 handle 查询创作者档案
     *
     * @param handle 创作者唯一标识
     * @return 匹配的创作者档案，可能为空
     */
    Optional<CreatorProfile> findByHandle(String handle);

    /**
     * 查询全部创作者档案，并按创建时间倒序排列
     *
     * @return 按创建时间从新到旧排列的创作者档案列表
     */
    List<CreatorProfile> findAllByOrderByCreatedAtDesc();

    /**
     * 判断指定 handle 的创作者档案是否已存在
     *
     * @param handle 创作者唯一标识
     * @return 存在返回 true，否则返回 false
     */
    boolean existsByHandle(String handle);
}
