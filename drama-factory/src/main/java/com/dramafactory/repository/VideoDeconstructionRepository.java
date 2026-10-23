package com.dramafactory.repository;

import com.dramafactory.model.VideoDeconstruction;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 视频拆解任务数据访问层。
 */
public interface VideoDeconstructionRepository extends JpaRepository<VideoDeconstruction, Long> {

    /**
     * 按项目 id 查询拆解任务，按创建时间降序排列。
     *
     * @param projectId 项目 id
     * @return 拆解任务列表
     */
    List<VideoDeconstruction> findByProjectIdOrderByCreatedAtDesc(Long projectId);
}
