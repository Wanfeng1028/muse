package com.dramafactory.repository;

import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * {@link Run} 仓库。
 */
public interface RunRepository extends JpaRepository<Run, Long> {

    /**
     * 按状态查询运行，按创建时间升序（执行器取 RUNNING 队列）。
     *
     * @param status 运行状态
     * @return 该状态的运行列表
     */
    List<Run> findByStatusOrderByCreatedAtAsc(RunStatus status);
}
