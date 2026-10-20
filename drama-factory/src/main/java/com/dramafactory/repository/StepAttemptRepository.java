package com.dramafactory.repository;

import com.dramafactory.model.StepAttempt;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

/** 步骤执行历史仓库接口 */
public interface StepAttemptRepository extends JpaRepository<StepAttempt, Long> {

    /** 统计指定步骤的尝试次数 */
    long countByStepId(Long stepId);

    /** 查询指定步骤的尝试历史，按尝试序号倒序 */
    List<StepAttempt> findByStepIdOrderByAttemptNoDesc(Long stepId);
}
