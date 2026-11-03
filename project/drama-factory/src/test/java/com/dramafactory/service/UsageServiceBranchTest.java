package com.dramafactory.service;

import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

class UsageServiceBranchTest {

    private final VideoTaskRepository videoTaskRepository = Mockito.mock(VideoTaskRepository.class);
    private final AgentStepRepository agentStepRepository = Mockito.mock(AgentStepRepository.class);
    private final RunRepository runRepository = Mockito.mock(RunRepository.class);
    private final UsageService usageService =
            new UsageService(videoTaskRepository, agentStepRepository, runRepository);

    private UsageService.RequestVideoRow videoRow(String provider, String model, Long tokens, LocalDateTime createdAt) {
        UsageService.RequestVideoRow r = Mockito.mock(UsageService.RequestVideoRow.class);
        when(r.getProvider()).thenReturn(provider);
        when(r.getModelUsed()).thenReturn(model);
        when(r.getTokensUsed()).thenReturn(tokens);
        when(r.getCreatedAt()).thenReturn(createdAt);
        return r;
    }

    private UsageService.RequestStepRow stepRow(AgentType label, Long tokens, LocalDateTime createdAt) {
        UsageService.RequestStepRow r = Mockito.mock(UsageService.RequestStepRow.class);
        when(r.getAgentLabel()).thenReturn(label);
        when(r.getTokensUsed()).thenReturn(tokens);
        when(r.getCreatedAt()).thenReturn(createdAt);
        return r;
    }

    // 覆盖 L80(m1c5)：summary 三参 provider 过滤 -> video 行 provider 不匹配 continue。
    @Test
    void branch2_summary_providerFilterSkipsMismatchedVideoRows() {
        LocalDateTime now = LocalDateTime.now();
        UsageService.RequestVideoRow row1 = videoRow("agnes", "m1", 100L, now);
        UsageService.RequestVideoRow row2 = videoRow("qwen", "m1", 200L, now);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row1,
                row2));
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());

        UsageService.UsageSummary filtered = usageService.summary("agnes", null, 0);
        assertEquals(1L, filtered.taskCount());
        assertEquals(100L, filtered.tokensTotal());

        // 注意：("", null, 0) 会命中 noFilter 快捷分支走 sum 查询；用 ("", "m1", 0) 进过滤分支，
        // 此时 provider 为空串不过滤 video 行（L80 的 !isEmpty() 为 false），model=m1 两行都命中
        UsageService.UsageSummary emptyProvider = usageService.summary("", "m1", 0);
        assertEquals(2L, emptyProvider.taskCount());
        assertEquals(300L, emptyProvider.tokensTotal());
    }

    // 覆盖 L83(m1c5)：summary 三参 model 过滤 -> video 行 modelUsed 不匹配 continue。
    @Test
    void branch2_summary_modelFilterSkipsMismatchedVideoRows() {
        LocalDateTime now = LocalDateTime.now();
        UsageService.RequestVideoRow row3 = videoRow("agnes", "m1", 100L, now);
        UsageService.RequestVideoRow row4 = videoRow("agnes", "m2", 200L, now);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row3,
                row4));
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());

        UsageService.UsageSummary s = usageService.summary(null, "m1", 0);
        assertEquals(1L, s.taskCount());
        assertEquals(100L, s.tokensTotal());
    }

    // 覆盖 L91(m1c3)：summary 三参 provider 非空时 step 行被整体跳过。
    @Test
    void branch2_summary_providerFilterSkipsAllStepRows() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());
        UsageService.RequestStepRow row5 = stepRow(AgentType.LYRICS, 50L, now);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row5));

        UsageService.UsageSummary withProvider = usageService.summary("agnes", null, 0);
        assertEquals(0L, withProvider.stepCount());

        // (null, null, 0) 命中 noFilter 快捷分支；用 model=中文 label 进过滤分支，
        // provider=null 时 step 行不被跳过（L91 的 provider != null 为 false）
        UsageService.UsageSummary noProvider = usageService.summary(null, AgentType.LYRICS.getLabel(), 0);
        assertEquals(1L, noProvider.stepCount());
        assertEquals(50L, noProvider.tokensTotal());
    }

    // 覆盖 L95(m2c4)：summary 三参 step 行 model 过滤与中文 label 比较。
    @Test
    void branch2_summary_stepModelFilterUsesAgentLabel() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());
        UsageService.RequestStepRow row6 = stepRow(AgentType.LYRICS, 50L, now);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row6));

        UsageService.UsageSummary match = usageService.summary(null, AgentType.LYRICS.getLabel(), 0);
        assertEquals(1L, match.stepCount());

        UsageService.UsageSummary noMatch = usageService.summary(null, "不存在的模型", 0);
        assertEquals(0L, noMatch.stepCount());
    }

    // 覆盖 L117(m1c5)：requests provider 过滤 -> video 行 provider 不匹配 continue。
    @Test
    void branch2_requests_providerFilterSkipsMismatchedVideoRows() {
        LocalDateTime now = LocalDateTime.now();
        UsageService.RequestVideoRow row7 = videoRow("agnes", "m1", 100L, now);
        UsageService.RequestVideoRow row8 = videoRow("qwen", "m1", 200L, now);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row7,
                row8));
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());

        List<UsageService.RequestUsage> result = usageService.requests(0, "qwen", null, 0);
        assertEquals(1, result.size());
        assertEquals("qwen", result.get(0).provider());
        assertEquals("VIDEO_TASK", result.get(0).kind());
    }

    // 覆盖 L120(m1c5)：requests model 过滤 -> video 行 modelUsed 不匹配 continue。
    @Test
    void branch2_requests_modelFilterSkipsMismatchedVideoRows() {
        LocalDateTime now = LocalDateTime.now();
        UsageService.RequestVideoRow row9 = videoRow("agnes", "m1", 100L, now);
        UsageService.RequestVideoRow row10 = videoRow("agnes", "m2", 200L, now);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row9,
                row10));
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());

        List<UsageService.RequestUsage> result = usageService.requests(0, null, "m2", 0);
        assertEquals(1, result.size());
        assertEquals("m2", result.get(0).model());
    }

    // 覆盖 L130(m1c3)：requests provider 非空时 step 行被整体跳过。
    @Test
    void branch2_requests_providerFilterSkipsAllStepRows() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());
        UsageService.RequestStepRow row11 = stepRow(AgentType.LYRICS, 50L, now);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row11));

        List<UsageService.RequestUsage> withProvider = usageService.requests(0, "agnes", null, 0);
        assertTrue(withProvider.isEmpty());

        List<UsageService.RequestUsage> noProvider = usageService.requests(0, null, null, 0);
        assertEquals(1, noProvider.size());
        assertEquals("AGENT_STEP", noProvider.get(0).kind());
    }

    // 覆盖 L134(m2c4)：requests step 行 model 过滤与中文 label 比较。
    @Test
    void branch2_requests_stepModelFilterUsesAgentLabel() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());
        UsageService.RequestStepRow row12 = stepRow(AgentType.LYRICS, 50L, now);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row12));

        List<UsageService.RequestUsage> match = usageService.requests(0, null, AgentType.LYRICS.getLabel(), 0);
        assertEquals(1, match.size());
        assertEquals("AGENT_STEP", match.get(0).kind());

        List<UsageService.RequestUsage> noMatch = usageService.requests(0, null, "不存在", 0);
        assertTrue(noMatch.isEmpty());
    }

    // 覆盖 L137(m1c1)：step 行 status null -> status 三元走 null 分支。
    @Test
    void branch2_requests_stepStatusNullProducesNullStatus() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of());
        UsageService.RequestStepRow row13 = stepRow(AgentType.LYRICS, 50L, now);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row13));

        List<UsageService.RequestUsage> result = usageService.requests(0, null, null, 0);
        assertEquals(1, result.size());
        assertNull(result.get(0).status());
    }

    // 覆盖 L146(m1c3)：排序比较器 ta/tb 双 null 返回 0，不抛错。
    @Test
    void branch2_requests_sortBothTimesNull() {
        UsageService.RequestVideoRow row14 = videoRow("agnes", "m1", 100L, null);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row14));
        UsageService.RequestStepRow row15 = stepRow(AgentType.LYRICS, 50L, null);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row15));

        List<UsageService.RequestUsage> result = usageService.requests(0, null, null, 0);
        assertEquals(2, result.size());
        assertNull(result.get(0).time());
        assertNull(result.get(1).time());
    }

    // 覆盖 L149(m1c1)：排序比较器 ta null 返回 1，null 时间排后。
    @Test
    void branch2_requests_sortNullTimeGoesLast() {
        LocalDateTime now = LocalDateTime.now();
        UsageService.RequestVideoRow row16 = videoRow("agnes", "m1", 100L, null);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row16));
        UsageService.RequestStepRow row17 = stepRow(AgentType.LYRICS, 50L, now);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(List.of(
                row17));

        List<UsageService.RequestUsage> result = usageService.requests(0, null, null, 0);
        assertEquals(2, result.size());
        assertEquals("AGENT_STEP", result.get(0).kind());
        assertNotNull(result.get(0).time());
        assertEquals("VIDEO_TASK", result.get(1).kind());
        assertNull(result.get(1).time());
    }

    // 覆盖 L174(m2c4)：byDay video 行 model 过滤。
    @Test
    void branch2_byDay_modelFilterSkipsMismatchedVideoRows() {
        LocalDateTime now = LocalDateTime.now();
        UsageService.VideoTaskRow r1 = Mockito.mock(UsageService.VideoTaskRow.class);
        when(r1.getModelUsed()).thenReturn("m1");
        when(r1.getTokensUsed()).thenReturn(100L);
        when(r1.getCostCents()).thenReturn(10L);
        when(r1.getCreatedAt()).thenReturn(now);
        UsageService.VideoTaskRow r2 = Mockito.mock(UsageService.VideoTaskRow.class);
        when(r2.getModelUsed()).thenReturn("m2");
        when(r2.getTokensUsed()).thenReturn(200L);
        when(r2.getCostCents()).thenReturn(20L);
        when(r2.getCreatedAt()).thenReturn(now);
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of(r1, r2));
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of());

        List<UsageService.DailyUsage> result = usageService.byDay(7, null, "m1");
        assertEquals(1, result.size());
        assertEquals(1L, result.get(0).videoCount());
        assertEquals(100L, result.get(0).tokens());
    }

    // 覆盖 L183(m1c3)：byDay provider 非空时 step 行被整体跳过。
    @Test
    void branch2_byDay_providerFilterSkipsAllStepRows() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of());
        UsageService.AgentStepRow s = Mockito.mock(UsageService.AgentStepRow.class);
        when(s.getAgentLabel()).thenReturn(AgentType.LYRICS);
        when(s.getTokensUsed()).thenReturn(50L);
        when(s.getCostCents()).thenReturn(5L);
        when(s.getCreatedAt()).thenReturn(now);
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of(s));

        List<UsageService.DailyUsage> withProvider = usageService.byDay(7, "agnes", null);
        assertTrue(withProvider.isEmpty());

        List<UsageService.DailyUsage> noProvider = usageService.byDay(7, null, null);
        assertEquals(1, noProvider.size());
        assertEquals(1L, noProvider.get(0).stepCount());
    }

    // 覆盖 L187(m5c1)：byDay step 行 model 过滤与中文 label 比较。
    @Test
    void branch2_byDay_stepModelFilterUsesAgentLabel() {
        LocalDateTime now = LocalDateTime.now();
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of());
        UsageService.AgentStepRow s = Mockito.mock(UsageService.AgentStepRow.class);
        when(s.getAgentLabel()).thenReturn(AgentType.LYRICS);
        when(s.getTokensUsed()).thenReturn(50L);
        when(s.getCostCents()).thenReturn(5L);
        when(s.getCreatedAt()).thenReturn(now);
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of(s));

        List<UsageService.DailyUsage> match = usageService.byDay(7, null, AgentType.LYRICS.getLabel());
        assertEquals(1, match.size());
        assertEquals(1L, match.get(0).stepCount());

        List<UsageService.DailyUsage> noMatch = usageService.byDay(7, null, "不存在");
        assertTrue(noMatch.isEmpty());
    }

    // 覆盖 L191/L192(m1c1×2)：byDay null 值按 0 合并。
    @Test
    void branch2_byDay_nullTokensAndCostMergedAsZero() {
        LocalDateTime now = LocalDateTime.now();
        UsageService.VideoTaskRow r = Mockito.mock(UsageService.VideoTaskRow.class);
        when(r.getModelUsed()).thenReturn("m1");
        when(r.getTokensUsed()).thenReturn(null);
        when(r.getCostCents()).thenReturn(null);
        when(r.getCreatedAt()).thenReturn(now);
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of(r));
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(List.of());

        List<UsageService.DailyUsage> result = usageService.byDay(7, null, null);
        assertEquals(1, result.size());
        assertEquals(0L, result.get(0).tokens());
        assertEquals(0L, result.get(0).costCents());
        assertEquals(1L, result.get(0).videoCount());
    }

    // 覆盖 L327-331(m1c1×4)：cacheHitRate null 归零与 total<=0 分支。
    @Test
    void branch2_summary_noArg_cacheHitRateNullAndZero() {
        when(videoTaskRepository.sumTokensUsed()).thenReturn(null);
        when(agentStepRepository.sumTokensUsed()).thenReturn(null);
        when(videoTaskRepository.sumCostCents()).thenReturn(null);
        when(agentStepRepository.sumCostCents()).thenReturn(null);
        when(videoTaskRepository.count()).thenReturn(0L);
        when(runRepository.count()).thenReturn(0L);
        when(agentStepRepository.count()).thenReturn(0L);
        when(videoTaskRepository.sumPromptTokens()).thenReturn(null);
        when(agentStepRepository.sumPromptTokens()).thenReturn(null);
        when(videoTaskRepository.sumCompletionTokens()).thenReturn(null);
        when(agentStepRepository.sumCompletionTokens()).thenReturn(null);
        when(videoTaskRepository.sumCachedTokens()).thenReturn(100L);
        when(agentStepRepository.sumCachedTokens()).thenReturn(null);

        UsageService.UsageSummary s = usageService.summary();
        assertEquals(100L, s.cachedTokensTotal());
        assertEquals(1.0, s.cacheHitRate());

        when(videoTaskRepository.sumCachedTokens()).thenReturn(null);
        UsageService.UsageSummary allNull = usageService.summary();
        assertEquals(0.0, allNull.cacheHitRate());
    }
}
