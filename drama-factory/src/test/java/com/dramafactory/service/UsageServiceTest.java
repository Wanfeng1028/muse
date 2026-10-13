
package com.dramafactory.service;

import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.model.AgentType;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;

import java.time.LocalDateTime;
import java.util.List;
import org.springframework.data.domain.PageRequest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * UsageService 单元测试（Mockito）：覆盖空库、空值跳过、byModel 分组。
 */
class UsageServiceTest {

    private VideoTaskRepository videoTaskRepository;
    private AgentStepRepository agentStepRepository;
    private RunRepository runRepository;
    private UsageService usageService;

    @BeforeEach
    void setUp() {
        videoTaskRepository = mock(VideoTaskRepository.class);
        agentStepRepository = mock(AgentStepRepository.class);
        runRepository = mock(RunRepository.class);
        usageService = new UsageService(videoTaskRepository, agentStepRepository, runRepository);
    }

    @Test
    void summary_emptyDatabase_returnsNullTotalsAndZeroCounts() {
        when(videoTaskRepository.sumTokensUsed()).thenReturn(null);
        when(agentStepRepository.sumTokensUsed()).thenReturn(null);
        when(videoTaskRepository.sumCostCents()).thenReturn(null);
        when(agentStepRepository.sumCostCents()).thenReturn(null);
        when(videoTaskRepository.count()).thenReturn(0L);
        when(runRepository.count()).thenReturn(0L);

        UsageService.UsageSummary summary = usageService.summary();

        assertThat(summary.tokensTotal()).isNull();
        assertThat(summary.costCentsTotal()).isNull();
        assertThat(summary.taskCount()).isZero();
        assertThat(summary.runCount()).isZero();
    }

    @Test
    void summary_sumsNonNullValues() {
        when(videoTaskRepository.sumTokensUsed()).thenReturn(100L);
        when(agentStepRepository.sumTokensUsed()).thenReturn(null);
        when(videoTaskRepository.sumCostCents()).thenReturn(null);
        when(agentStepRepository.sumCostCents()).thenReturn(250L);
        when(videoTaskRepository.count()).thenReturn(2L);
        when(runRepository.count()).thenReturn(1L);

        UsageService.UsageSummary summary = usageService.summary();

        assertThat(summary.tokensTotal()).isEqualTo(100L);
        assertThat(summary.costCentsTotal()).isEqualTo(250L);
        assertThat(summary.taskCount()).isEqualTo(2L);
        assertThat(summary.runCount()).isEqualTo(1L);
    }

    @Test
    void byModel_emptyDatabase_returnsEmptyList() {
        when(videoTaskRepository.findAllForModelUsage()).thenReturn(List.of());
        when(agentStepRepository.findAllForModelUsage()).thenReturn(List.of());

        List<UsageService.ModelUsage> result = usageService.byModel();

        assertThat(result).isEmpty();
    }

    @Test
    void byModel_groupsByModelAndSkipsNullTokens() {
        // 两个 VideoTask：model A 一个 100 tokens，另一个 tokensUsed=null（跳过求和但计数 +1）
        UsageService.VideoTaskRow rowA1 = videoRow("model-A", 100L, 10L, LocalDateTime.now());
        UsageService.VideoTaskRow rowA2 = videoRow("model-A", null, null, LocalDateTime.now());
        UsageService.VideoTaskRow rowB = videoRow("model-B", 50L, 5L, LocalDateTime.now());

        when(videoTaskRepository.findAllForModelUsage()).thenReturn(List.of(rowA1, rowA2, rowB));

        UsageService.AgentStepRow step = stepRow(AgentType.VIDEO, 200L, 20L, LocalDateTime.now());
        when(agentStepRepository.findAllForModelUsage()).thenReturn(List.of(step));

        List<UsageService.ModelUsage> result = usageService.byModel();

        assertThat(result).hasSize(3);

        UsageService.ModelUsage modelA = result.stream()
                .filter(m -> "model-A".equals(m.model())).findFirst().orElseThrow();
        assertThat(modelA.tokens()).isEqualTo(100L);
        assertThat(modelA.costCents()).isEqualTo(10L);
        assertThat(modelA.taskCount()).isEqualTo(2L);

        UsageService.ModelUsage modelB = result.stream()
                .filter(m -> "model-B".equals(m.model())).findFirst().orElseThrow();
        assertThat(modelB.tokens()).isEqualTo(50L);
        assertThat(modelB.costCents()).isEqualTo(5L);
        assertThat(modelB.taskCount()).isEqualTo(1L);

        UsageService.ModelUsage agentGroup = result.stream()
                .filter(m -> "视频生成".equals(m.model())).findFirst().orElseThrow();
        assertThat(agentGroup.tokens()).isEqualTo(200L);
        assertThat(agentGroup.costCents()).isEqualTo(20L);
        assertThat(agentGroup.taskCount()).isEqualTo(1L);
    }

    @Test
    void byDay_emptyDatabase_returnsEmptyList() {
        when(videoTaskRepository.findForDailyUsage(ArgumentMatchers.any(LocalDateTime.class)))
                .thenReturn(List.of());
        when(agentStepRepository.findForDailyUsage(ArgumentMatchers.any(LocalDateTime.class)))
                .thenReturn(List.of());

        List<UsageService.DailyUsage> result = usageService.byDay(30);

        assertThat(result).isEmpty();
    }

    @Test
    void byRun_emptyDatabase_returnsEmptyList() {
        when(runRepository.findAllByOrderByCreatedAtDesc(ArgumentMatchers.any(PageRequest.class))).thenReturn(List.of());

        List<UsageService.RunUsage> result = usageService.byRun(20);

        assertThat(result).isEmpty();
    }

    @Test
    void byRun_fallsBackToAgentStepSumWhenRunTotalsNull() {
        UsageService.RunRow run = runRow(7L, "一个很长很长的目标描述超过了三十个字符限制需要被截断再加几个字凑够",
                null, null, LocalDateTime.now());
        when(runRepository.findAllByOrderByCreatedAtDesc(ArgumentMatchers.any(PageRequest.class))).thenReturn(List.of(run));
        when(agentStepRepository.sumTokensUsedByRunId(7L)).thenReturn(300L);
        when(agentStepRepository.sumCostCentsByRunId(7L)).thenReturn(30L);

        List<UsageService.RunUsage> result = usageService.byRun(20);

        assertThat(result).hasSize(1);
        UsageService.RunUsage r = result.get(0);
        assertThat(r.runId()).isEqualTo(7L);
        assertThat(r.tokens()).isEqualTo(300L);
        assertThat(r.costCents()).isEqualTo(30L);
        assertThat(r.goal()).hasSize(30);
    }

    // ==== 辅助工厂 ====

    private static UsageService.VideoTaskRow videoRow(String model, Long tokens, Long cost, LocalDateTime createdAt) {
        return new UsageService.VideoTaskRow() {
            @Override public String getModelUsed() { return model; }
            @Override public Long getTokensUsed() { return tokens; }
            @Override public Long getCostCents() { return cost; }
            @Override public LocalDateTime getCreatedAt() { return createdAt; }
        };
    }

    private static UsageService.AgentStepRow stepRow(AgentType type, Long tokens, Long cost, LocalDateTime createdAt) {
        return new UsageService.AgentStepRow() {
            @Override public AgentType getAgentLabel() { return type; }
            @Override public Long getTokensUsed() { return tokens; }
            @Override public Long getCostCents() { return cost; }
            @Override public LocalDateTime getCreatedAt() { return createdAt; }
        };
    }

    private static UsageService.RunRow runRow(Long id, String goal, Long tokens, Long cost, LocalDateTime createdAt) {
        return new UsageService.RunRow() {
            @Override public Long getId() { return id; }
            @Override public String getGoal() { return goal; }
            @Override public Long getTotalTokens() { return tokens; }
            @Override public Long getTotalCostCents() { return cost; }
            @Override public LocalDateTime getCreatedAt() { return createdAt; }
        };
    }
}
