package com.dramafactory.repository;

import com.dramafactory.model.AgentStep;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import com.dramafactory.service.UsageService;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.time.LocalDateTime;

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


    @Query("SELECT SUM(s.tokensUsed) FROM AgentStep s")
    Long sumTokensUsed();

    @Query("SELECT SUM(s.costCents) FROM AgentStep s")
    Long sumCostCents();

    @Query("SELECT SUM(s.tokensUsed) FROM AgentStep s WHERE s.run.id = :runId")
    Long sumTokensUsedByRunId(@Param("runId") Long runId);

    @Query("SELECT SUM(s.costCents) FROM AgentStep s WHERE s.run.id = :runId")
    Long sumCostCentsByRunId(@Param("runId") Long runId);

    @Query("SELECT s.agentType AS agentLabel, s.tokensUsed AS tokensUsed, s.costCents AS costCents, s.createdAt AS createdAt FROM AgentStep s")
    List<UsageService.AgentStepRow> findAllForModelUsage();

    @Query("SELECT s.agentType AS agentLabel, s.tokensUsed AS tokensUsed, s.costCents AS costCents, s.createdAt AS createdAt FROM AgentStep s WHERE s.createdAt >= :from")
    List<UsageService.AgentStepRow> findForDailyUsage(@Param("from") LocalDateTime from);
}
