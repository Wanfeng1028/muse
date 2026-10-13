package com.dramafactory.repository;

import com.dramafactory.model.AgentStep;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * {@link AgentStep} 仓库。
 */
public interface AgentStepRepository extends JpaRepository<AgentStep, Long> {

    /**
     * 按所属运行 ID 升序返回步骤。
     *
     * @param runId 运行 ID
     * @return 按 seqNo 升序排列的步骤列表
     */
    List<AgentStep> findByRunIdOrderBySeqNoAsc(Long runId);
}
