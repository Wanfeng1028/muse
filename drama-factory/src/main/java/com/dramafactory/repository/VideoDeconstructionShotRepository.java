package com.dramafactory.repository;

import com.dramafactory.model.VideoDeconstructionShot;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 视频拆解逐镜结果数据访问层。
 */
public interface VideoDeconstructionShotRepository extends JpaRepository<VideoDeconstructionShot, Long> {

    /**
     * 按拆解任务 id 查询逐镜结果，按镜号升序排列。
     *
     * @param deconstructionId 拆解任务 id
     * @return 逐镜结果列表
     */
    List<VideoDeconstructionShot> findByDeconstructionIdOrderByShotNoAsc(Long deconstructionId);

    /**
     * 按拆解任务 id 删除全部逐镜结果。
     *
     * @param deconstructionId 拆解任务 id
     */
    void deleteByDeconstructionId(Long deconstructionId);
}
