
package com.dramafactory.service;

import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.ArgumentMatchers;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import org.springframework.data.domain.PageRequest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
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

    @Test
    void requests_空库返回空集合() {
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());
        List<UsageService.RequestUsage> result = usageService.requests(50, null, null, 30);
        assertThat(result).isEmpty();
    }

    @Test
    void requests_合并排序与过滤() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                requestVideoRow(1L, "openai", "gpt-4o", 100L, 5L, false, VideoTaskStatus.DONE, now.minusHours(1)),
                requestVideoRow(2L, "anthropic", "claude-3", 200L, 8L, false, VideoTaskStatus.DONE, now.minusHours(3))));
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                requestStepRow(3L, AgentType.VIDEO, 300L, 10L, false, 1200L, AgentStepStatus.SUCCEEDED, now.minusHours(2))));
        List<UsageService.RequestUsage> all = usageService.requests(50, null, null, 30);
        assertThat(all).hasSize(3);
        assertThat(all.get(0).id()).isEqualTo(1L);
        assertThat(all.get(1).id()).isEqualTo(3L);
        assertThat(all.get(2).id()).isEqualTo(2L);

        List<UsageService.RequestUsage> byProvider = usageService.requests(50, "openai", null, 30);
        assertThat(byProvider).hasSize(1);
        assertThat(byProvider.get(0).id()).isEqualTo(1L);

        List<UsageService.RequestUsage> byModel = usageService.requests(50, null, "claude-3", 30);
        assertThat(byModel).hasSize(1);
        assertThat(byModel.get(0).id()).isEqualTo(2L);
    }

    @Test
    void summary_带过滤按行求和() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                requestVideoRow(1L, "openai", "gpt-4o", 100L, 5L, false, VideoTaskStatus.DONE, now),
                requestVideoRow(2L, "openai", "gpt-4o", 200L, 8L, false, VideoTaskStatus.DONE, now)));
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                requestStepRow(3L, AgentType.VIDEO, 300L, 10L, false, 1200L, AgentStepStatus.SUCCEEDED, now)));
        UsageService.UsageSummary s = usageService.summary("openai", "gpt-4o", 30);
        assertThat(s.tokensTotal()).isEqualTo(300L);
        assertThat(s.costCentsTotal()).isEqualTo(13L);
        assertThat(s.taskCount()).isEqualTo(2L);
        assertThat(s.stepCount()).isZero();
        assertThat(s.requestCount()).isEqualTo(2L);
    }

    @Test
    void byDay_带计数() {
        LocalDate today = LocalDate.now();
        LocalDateTime ts = today.atTime(10, 0);
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of(
                videoRow("gpt-4o", 100L, 5L, ts),
                videoRow("gpt-4o", 50L, 2L, ts)));
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of(
                stepRow(AgentType.VIDEO, 30L, 1L, ts)));
        List<UsageService.DailyUsage> result = usageService.byDay(30, null, null);
        assertThat(result).hasSize(1);
        assertThat(result.get(0).videoCount()).isEqualTo(2L);
        assertThat(result.get(0).stepCount()).isEqualTo(1L);
    }

    @Test
    void filters_去重合并() {
        when(videoTaskRepository.findDistinctProviders()).thenReturn(List.of("openai", "openai", "anthropic"));
        when(videoTaskRepository.findDistinctModels()).thenReturn(List.of("gpt-4o", "gpt-4o"));
        when(agentStepRepository.findDistinctAgentTypes()).thenReturn(List.of(AgentType.VIDEO));
        UsageService.FilterOptions f = usageService.filters();
        assertThat(f.providers()).containsExactly("anthropic", "openai");
        assertThat(f.models()).contains("gpt-4o");
        assertThat(f.models()).contains(AgentType.VIDEO.getLabel());
    }

    @Test
    void A1_summary三参全空走快速路径() {
        when(videoTaskRepository.sumTokensUsed()).thenReturn(null);
        when(agentStepRepository.sumTokensUsed()).thenReturn(null);
        when(videoTaskRepository.sumCostCents()).thenReturn(null);
        when(agentStepRepository.sumCostCents()).thenReturn(null);
        when(videoTaskRepository.count()).thenReturn(3L);
        when(runRepository.count()).thenReturn(2L);
        when(agentStepRepository.count()).thenReturn(5L);

        UsageService.UsageSummary s = usageService.summary(null, null, 0);

        assertThat(s.tokensTotal()).isNull();
        assertThat(s.costCentsTotal()).isNull();
        assertThat(s.taskCount()).isEqualTo(3L);
        assertThat(s.runCount()).isEqualTo(2L);
        assertThat(s.stepCount()).isEqualTo(5L);
        assertThat(s.requestCount()).isEqualTo(8L);
    }

    @Test
    void A2_summary三参空字符串走快速路径() {
        when(videoTaskRepository.sumTokensUsed()).thenReturn(null);
        when(agentStepRepository.sumTokensUsed()).thenReturn(null);
        when(videoTaskRepository.sumCostCents()).thenReturn(null);
        when(agentStepRepository.sumCostCents()).thenReturn(null);
        when(videoTaskRepository.count()).thenReturn(3L);
        when(runRepository.count()).thenReturn(2L);
        when(agentStepRepository.count()).thenReturn(5L);

        UsageService.UsageSummary s = usageService.summary("", "", -5);

        assertThat(s.tokensTotal()).isNull();
        assertThat(s.costCentsTotal()).isNull();
        assertThat(s.taskCount()).isEqualTo(3L);
        assertThat(s.runCount()).isEqualTo(2L);
        assertThat(s.stepCount()).isEqualTo(5L);
        assertThat(s.requestCount()).isEqualTo(8L);
    }

    @Test
    void A3_summary过滤路径days正数() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "openai", "gpt-4o", 100L, 5L, false, VideoTaskStatus.DONE, now),
                requestVideoRow(2L, "openai", "gpt-4o", 200L, 8L, false, VideoTaskStatus.DONE, now)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of(
                requestStepRow(3L, AgentType.VIDEO, 300L, 10L, false, 5L, AgentStepStatus.SUCCEEDED, now)));

        UsageService.UsageSummary s = usageService.summary("openai", null, 30);

        assertThat(s.taskCount()).isEqualTo(2L);
        assertThat(s.stepCount()).isEqualTo(0L);
        assertThat(s.tokensTotal()).isEqualTo(300L);
        assertThat(s.costCentsTotal()).isEqualTo(13L);
        assertThat(s.requestCount()).isEqualTo(2L);
    }

    @Test
    void A4_summary过滤路径days非正() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "openai", "m", 50L, 2L, false, VideoTaskStatus.DONE, now)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of());

        UsageService.UsageSummary s = usageService.summary("openai", null, 0);

        assertThat(s.taskCount()).isEqualTo(1L);
        assertThat(s.tokensTotal()).isEqualTo(50L);
        assertThat(s.costCentsTotal()).isEqualTo(2L);
    }

    @Test
    void A5_video行provider不匹配被跳过() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "anthropic", "m", 50L, 2L, false, VideoTaskStatus.DONE, now)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of());

        UsageService.UsageSummary s = usageService.summary("openai", null, 30);

        assertThat(s.taskCount()).isEqualTo(0L);
        assertThat(s.tokensTotal()).isNull();
        assertThat(s.requestCount()).isEqualTo(0L);
    }

    @Test
    void A6_video行model不匹配被跳过() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "openai", "claude", 50L, 2L, false, VideoTaskStatus.DONE, now)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of());

        UsageService.UsageSummary s = usageService.summary(null, "gpt-4o", 30);

        assertThat(s.taskCount()).isEqualTo(0L);
        assertThat(s.tokensTotal()).isNull();
    }

    @Test
    void A7_video行空tokens累加() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "openai", "m", null, null, false, VideoTaskStatus.DONE, now)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of());

        UsageService.UsageSummary s = usageService.summary(null, null, 30);

        assertThat(s.taskCount()).isEqualTo(1L);
        assertThat(s.tokensTotal()).isNull();
        assertThat(s.costCentsTotal()).isNull();
    }

    @Test
    void A8_step行provider非空全跳过() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of());
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of(
                requestStepRow(3L, AgentType.VIDEO, 300L, 10L, false, 5L, AgentStepStatus.SUCCEEDED, now)));

        UsageService.UsageSummary s = usageService.summary("x", null, 30);

        assertThat(s.stepCount()).isEqualTo(0L);
        assertThat(s.tokensTotal()).isNull();
        assertThat(s.requestCount()).isEqualTo(0L);
    }

    @Test
    void A9_step行label为null被计入() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of());
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of(
                requestStepRow(3L, null, 300L, 10L, false, 5L, AgentStepStatus.SUCCEEDED, now)));

        UsageService.UsageSummary s = usageService.summary(null, null, 30);

        assertThat(s.stepCount()).isEqualTo(1L);
        assertThat(s.tokensTotal()).isEqualTo(300L);
        assertThat(s.costCentsTotal()).isEqualTo(10L);
    }

    @Test
    void A10_step行model不匹配被跳过() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of());
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of(
                requestStepRow(3L, AgentType.VIDEO, 300L, 10L, false, 5L, AgentStepStatus.SUCCEEDED, now)));

        UsageService.UsageSummary s = usageService.summary(null, "gpt-4o", 30);

        assertThat(s.stepCount()).isEqualTo(0L);
        assertThat(s.tokensTotal()).isNull();
    }

    @Test
    void B1_requests跳过modelUsed为null的video行() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "p", null, 1L, 1L, false, VideoTaskStatus.DONE, now)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of());

        List<UsageService.RequestUsage> result = usageService.requests(50, null, null, 30);

        assertThat(result).isEmpty();
    }

    @Test
    void B2_requests的step行label为null() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of());
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of(
                requestStepRow(2L, null, 5L, 1L, false, 9L, AgentStepStatus.SUCCEEDED, now)));

        List<UsageService.RequestUsage> result = usageService.requests(50, null, null, 30);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).model()).isNull();
        assertThat(result.get(0).kind()).isEqualTo("AGENT_STEP");
    }

    @Test
    void B3_requests的step行model不匹配() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of());
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of(
                requestStepRow(2L, AgentType.VIDEO, 5L, 1L, false, 9L, AgentStepStatus.SUCCEEDED, now)));

        List<UsageService.RequestUsage> result = usageService.requests(50, null, "zzz", 30);

        assertThat(result).isEmpty();
    }

    @Test
    void B4_requests的video行status为null() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "p", "m", 1L, 1L, false, null, now)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of());

        List<UsageService.RequestUsage> result = usageService.requests(50, null, null, 30);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).status()).isNull();
        assertThat(result.get(0).model()).isEqualTo("m");
    }

    @Test
    void B5_requests排序null时间() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "p", "m", 1L, 1L, false, VideoTaskStatus.DONE, null),
                requestVideoRow(2L, "p", "m", 1L, 1L, false, VideoTaskStatus.DONE, null)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of());

        List<UsageService.RequestUsage> bothNull = usageService.requests(50, null, null, 30);
        assertThat(bothNull).hasSize(2);

        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "p", "m", 1L, 1L, false, VideoTaskStatus.DONE, null),
                requestVideoRow(2L, "p", "m", 1L, 1L, false, VideoTaskStatus.DONE, now)));

        List<UsageService.RequestUsage> mixed = usageService.requests(50, null, null, 30);
        assertThat(mixed).hasSize(2);
        assertThat(mixed.get(0).time()).isEqualTo(now);
        assertThat(mixed.get(1).time()).isNull();
    }

    @Test
    void B6_requests限流截断() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any())).thenReturn(List.of(
                requestVideoRow(1L, "p", "m", 1L, 1L, false, VideoTaskStatus.DONE, now),
                requestVideoRow(2L, "p", "m", 1L, 1L, false, VideoTaskStatus.DONE, now),
                requestVideoRow(3L, "p", "m", 1L, 1L, false, VideoTaskStatus.DONE, now)));
        when(agentStepRepository.findForRequests(any())).thenReturn(List.of());

        assertThat(usageService.requests(1, null, null, 30)).hasSize(1);
        assertThat(usageService.requests(0, null, null, 30)).hasSize(3);
    }

    @Test
    void C1_byDay的video行model不匹配() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForDailyUsage(any())).thenReturn(List.of(
                videoRow("gpt-4o", 100L, 5L, now)));
        when(agentStepRepository.findForDailyUsage(any())).thenReturn(List.of());

        List<UsageService.DailyUsage> result = usageService.byDay(30, null, "zzz");

        assertThat(result).isEmpty();
    }

    @Test
    void C2_byDay的step行provider非空跳过() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForDailyUsage(any())).thenReturn(List.of());
        when(agentStepRepository.findForDailyUsage(any())).thenReturn(List.of(
                stepRow(AgentType.VIDEO, 30L, 1L, now)));

        List<UsageService.DailyUsage> result = usageService.byDay(30, "openai", null);

        assertThat(result).isEmpty();
    }

    @Test
    void C3_byDay空tokens按0合并() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForDailyUsage(any())).thenReturn(List.of(
                videoRow("m", null, null, now)));
        when(agentStepRepository.findForDailyUsage(any())).thenReturn(List.of());

        List<UsageService.DailyUsage> result = usageService.byDay(30, null, null);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).tokens()).isEqualTo(0L);
        assertThat(result.get(0).costCents()).isEqualTo(0L);
        assertThat(result.get(0).videoCount()).isEqualTo(1L);
    }

    @Test
    void C4_byDay负天数用默认() {
        when(videoTaskRepository.findForDailyUsage(any())).thenReturn(List.of());
        when(agentStepRepository.findForDailyUsage(any())).thenReturn(List.of());

        List<UsageService.DailyUsage> result = usageService.byDay(-1, null, null);

        assertThat(result).isEmpty();
    }

    @Test
    void C5_byDay的step行label为null计入() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForDailyUsage(any())).thenReturn(List.of());
        when(agentStepRepository.findForDailyUsage(any())).thenReturn(List.of(
                stepRow(null, 30L, 1L, now)));

        List<UsageService.DailyUsage> result = usageService.byDay(30, null, null);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).stepCount()).isEqualTo(1L);
        assertThat(result.get(0).tokens()).isEqualTo(30L);
    }

    @Test
    void D1_byRun的limit非正用默认20() {
        when(runRepository.findAllByOrderByCreatedAtDesc(any())).thenReturn(List.of());

        usageService.byRun(0);

        ArgumentCaptor<PageRequest> captor = ArgumentCaptor.forClass(PageRequest.class);
        verify(runRepository).findAllByOrderByCreatedAtDesc(captor.capture());
        assertThat(captor.getValue().getPageSize()).isEqualTo(20);
        assertThat(captor.getValue().getPageNumber()).isEqualTo(0);
    }

    @Test
    void D2_byRun直接用Run自带总量() {
        LocalDateTime now = LocalDateTime.now();
        when(runRepository.findAllByOrderByCreatedAtDesc(any())).thenReturn(List.of(
                runRow(8L, "短目标", 500L, 50L, now)));

        List<UsageService.RunUsage> result = usageService.byRun(10);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).tokens()).isEqualTo(500L);
        assertThat(result.get(0).costCents()).isEqualTo(50L);
        assertThat(result.get(0).goal()).isEqualTo("短目标");
        verify(agentStepRepository, never()).sumTokensUsedByRunId(any());
    }

    @Test
    void D3_byRun的goal为null() {
        LocalDateTime now = LocalDateTime.now();
        when(runRepository.findAllByOrderByCreatedAtDesc(any())).thenReturn(List.of(
                runRow(9L, null, 100L, 10L, now)));

        List<UsageService.RunUsage> result = usageService.byRun(10);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).goal()).isNull();
        assertThat(result.get(0).tokens()).isEqualTo(100L);
        assertThat(result.get(0).costCents()).isEqualTo(10L);
    }

    @Test
    void E1_byModel跳过model为null的video行() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findAllForModelUsage()).thenReturn(List.of(
                videoRow(null, 100L, 5L, now)));
        when(agentStepRepository.findAllForModelUsage()).thenReturn(List.of());

        assertThat(usageService.byModel()).isEmpty();
    }

    @Test
    void E2_byModel跳过label为null的step行() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findAllForModelUsage()).thenReturn(List.of());
        when(agentStepRepository.findAllForModelUsage()).thenReturn(List.of(
                stepRow(null, 100L, 5L, now)));

        assertThat(usageService.byModel()).isEmpty();
    }

    @Test
    void F1_filters跳过null的AgentType() {
        when(videoTaskRepository.findDistinctProviders()).thenReturn(List.of("openai"));
        when(videoTaskRepository.findDistinctModels()).thenReturn(List.of("gpt-4o"));
        when(agentStepRepository.findDistinctAgentTypes()).thenReturn(Arrays.asList(AgentType.VIDEO, null));

        UsageService.FilterOptions options = usageService.filters();

        assertThat(options.providers()).containsExactly("openai");
        assertThat(options.models()).contains("gpt-4o", "视频生成").doesNotContainNull();
    }

    // ==== 辅助工厂 ====


    private static UsageService.RequestVideoRow requestVideoRow(Long id, String provider, String model,
                                                         Long tokens, Long cost, Boolean estimated,
                                                         VideoTaskStatus status, LocalDateTime createdAt) {
        return new UsageService.RequestVideoRow() {
            @Override public Long getId() { return id; }
            @Override public String getProvider() { return provider; }
            @Override public String getModelUsed() { return model; }
            @Override public Long getTokensUsed() { return tokens; }
            @Override public Long getPromptTokens() { return 0L; }
            @Override public Long getCompletionTokens() { return 0L; }
            @Override public Long getCachedTokens() { return 0L; }
            @Override public Long getCostCents() { return cost; }
            @Override public Boolean getCostEstimated() { return estimated; }
            @Override public VideoTaskStatus getStatus() { return status; }
            @Override public LocalDateTime getCreatedAt() { return createdAt; }
        };
    }

    private static UsageService.RequestStepRow requestStepRow(Long id, AgentType agentType, Long tokens, Long cost,
                                                       Boolean estimated, Long latencyMs,
                                                       AgentStepStatus status, LocalDateTime createdAt) {
        return new UsageService.RequestStepRow() {
            @Override public Long getId() { return id; }
            @Override public AgentType getAgentLabel() { return agentType; }
            @Override public Long getTokensUsed() { return tokens; }
            @Override public Long getPromptTokens() { return 0L; }
            @Override public Long getCompletionTokens() { return 0L; }
            @Override public Long getCachedTokens() { return 0L; }
            @Override public Long getCostCents() { return cost; }
            @Override public Boolean getCostEstimated() { return estimated; }
            @Override public Long getLatencyMs() { return latencyMs; }
            @Override public AgentStepStatus getStatus() { return status; }
            @Override public LocalDateTime getCreatedAt() { return createdAt; }
        };
    }

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
