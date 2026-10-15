package com.dramafactory.service;

import com.dramafactory.model.AgentType;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UsageServiceV223ATest {

    @Mock
    private VideoTaskRepository videoTaskRepository;

    @Mock
    private AgentStepRepository agentStepRepository;

    @Mock
    private RunRepository runRepository;

    private UsageService usageService;

    @BeforeEach
    void setUp() {
        usageService = new UsageService(videoTaskRepository, agentStepRepository, runRepository);
    }

    // helper 的 stub 按需触发：空串过滤测试里 filter 短路，getter 永不被调用，故用 lenient（各用例仍做真实行为断言）。
    private UsageService.RequestVideoRow videoRow(String provider, String model, Long tokens,
                                                  VideoTaskStatus status, LocalDateTime createdAt) {
        UsageService.RequestVideoRow row = org.mockito.Mockito.mock(UsageService.RequestVideoRow.class);
        lenient().when(row.getProvider()).thenReturn(provider);
        lenient().when(row.getModelUsed()).thenReturn(model);
        lenient().when(row.getTokensUsed()).thenReturn(tokens);
        lenient().when(row.getStatus()).thenReturn(status);
        lenient().when(row.getCreatedAt()).thenReturn(createdAt);
        return row;
    }

    private UsageService.RequestStepRow stepRow(AgentType label, Long tokens,
                                                AgentStepStatus status, LocalDateTime createdAt) {
        UsageService.RequestStepRow row = org.mockito.Mockito.mock(UsageService.RequestStepRow.class);
        lenient().when(row.getAgentLabel()).thenReturn(label);
        lenient().when(row.getTokensUsed()).thenReturn(tokens);
        lenient().when(row.getStatus()).thenReturn(status);
        lenient().when(row.getCreatedAt()).thenReturn(createdAt);
        return row;
    }

    // ① summary(null,"",0) 视频行 model 空串不过滤：L83 缺失臂 model=""
    @Test
    void summaryVideoLoop_modelEmptyString_doesNotFilter() {
        UsageService.RequestVideoRow v = videoRow("p1", "m1", 5L, null, LocalDateTime.now());
        List<UsageService.RequestVideoRow> videoRows = new ArrayList<>();
        videoRows.add(v);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(videoRows);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());

        UsageService.UsageSummary result = usageService.summary(null, "", 1);

        assertEquals(1L, result.taskCount());
        assertEquals(5L, result.tokensTotal());
    }

    // ② summary("",null,0) 步骤行 provider 空串不过滤：L91 缺失臂 provider=""
    @Test
    void summaryStepLoop_providerEmptyString_doesNotFilter() {
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());
        UsageService.RequestStepRow s = stepRow(AgentType.SCRIPT, 7L, null, LocalDateTime.now());
        List<UsageService.RequestStepRow> stepRows = new ArrayList<>();
        stepRows.add(s);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(stepRows);

        UsageService.UsageSummary result = usageService.summary("", null, 1);

        assertEquals(1L, result.stepCount());
        assertEquals(7L, result.tokensTotal());
    }

    // ③ summary(null,"",0) 步骤行 model 空串不过滤：L95 缺失臂 model=""
    @Test
    void summaryStepLoop_modelEmptyString_doesNotFilter() {
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());
        UsageService.RequestStepRow s = stepRow(AgentType.SCRIPT, 9L, null, LocalDateTime.now());
        List<UsageService.RequestStepRow> stepRows = new ArrayList<>();
        stepRows.add(s);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(stepRows);

        UsageService.UsageSummary result = usageService.summary(null, "", 1);

        assertEquals(1L, result.stepCount());
        assertEquals(9L, result.tokensTotal());
    }

    // ④ requests(10,"",null,0) 视频循环 provider 空串不过滤：L117 缺失臂 provider=""
    @Test
    void requestsVideoLoop_providerEmptyString_doesNotFilter() {
        UsageService.RequestVideoRow v = videoRow("p1", "m1", 5L, null, LocalDateTime.now());
        List<UsageService.RequestVideoRow> videoRows = new ArrayList<>();
        videoRows.add(v);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(videoRows);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());

        List<UsageService.RequestUsage> result = usageService.requests(10, "", null, 0);

        assertEquals(1, result.size());
        assertEquals("VIDEO_TASK", result.get(0).kind());
    }

    // ⑤ requests(10,null,"",0) 视频循环 model 空串不过滤：L120 缺失臂 model=""
    @Test
    void requestsVideoLoop_modelEmptyString_doesNotFilter() {
        UsageService.RequestVideoRow v = videoRow("p1", "m1", 5L, null, LocalDateTime.now());
        List<UsageService.RequestVideoRow> videoRows = new ArrayList<>();
        videoRows.add(v);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(videoRows);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());

        List<UsageService.RequestUsage> result = usageService.requests(10, null, "", 0);

        assertEquals(1, result.size());
    }

    // ⑥a requests 步骤循环 provider 空串不过滤：L130 缺失臂 provider=""
    @Test
    void requestsStepLoop_providerEmptyString_doesNotFilter() {
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());
        UsageService.RequestStepRow s = stepRow(AgentType.SCRIPT, 5L, null, LocalDateTime.now());
        List<UsageService.RequestStepRow> stepRows = new ArrayList<>();
        stepRows.add(s);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(stepRows);

        List<UsageService.RequestUsage> result = usageService.requests(10, "", null, 0);

        assertEquals(1, result.size());
        assertEquals("AGENT_STEP", result.get(0).kind());
    }

    // ⑥b requests 步骤循环 model 空串不过滤：L134 缺失臂 model=""
    @Test
    void requestsStepLoop_modelEmptyString_doesNotFilter() {
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());
        UsageService.RequestStepRow s = stepRow(AgentType.SCRIPT, 5L, null, LocalDateTime.now());
        List<UsageService.RequestStepRow> stepRows = new ArrayList<>();
        stepRows.add(s);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(stepRows);

        List<UsageService.RequestUsage> result = usageService.requests(10, null, "", 0);

        assertEquals(1, result.size());
    }

    // ⑦ requests 两行 createdAt 都 null：L146 双 null 臂
    @Test
    void requestsComparator_bothTimesNull_returnsBothUnchanged() {
        UsageService.RequestVideoRow v1 = videoRow("p1", "m1", 1L, null, null);
        UsageService.RequestVideoRow v2 = videoRow("p1", "m1", 2L, null, null);
        List<UsageService.RequestVideoRow> videoRows = new ArrayList<>();
        videoRows.add(v1);
        videoRows.add(v2);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(videoRows);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());

        List<UsageService.RequestUsage> result = usageService.requests(10, null, null, 0);

        assertEquals(2, result.size());
    }

    // ⑧ requests 第一行有时间、第二行 null：L149 ta 非 null 臂
    @Test
    void requestsComparator_firstTimeNonNullSecondNull() {
        LocalDateTime now = LocalDateTime.now();
        UsageService.RequestVideoRow v1 = videoRow("p1", "m1", 1L, null, now);
        UsageService.RequestVideoRow v2 = videoRow("p1", "m1", 2L, null, null);
        List<UsageService.RequestVideoRow> videoRows = new ArrayList<>();
        videoRows.add(v1);
        videoRows.add(v2);
        when(videoTaskRepository.findForRequests(any(LocalDateTime.class))).thenReturn(videoRows);
        when(agentStepRepository.findForRequests(any(LocalDateTime.class))).thenReturn(new ArrayList<>());

        List<UsageService.RequestUsage> result = usageService.requests(10, null, null, 0);

        assertEquals(2, result.size());
        assertNotNull(result.get(0).time());
    }

    // ⑨a byDay(7,null,"") 视频行 model 空串不过滤：L174 缺失臂 model=""
    @Test
    void byDayVideoLoop_modelEmptyString_doesNotFilter() {
        UsageService.VideoTaskRow r = org.mockito.Mockito.mock(UsageService.VideoTaskRow.class);
        // 注意：model="" 时 L174 在 !isEmpty() 处短路，getModelUsed() 永不被调用，故不 stub（否则 strict-stubs 报错）。
        when(r.getTokensUsed()).thenReturn(5L);
        when(r.getCostCents()).thenReturn(2L);
        when(r.getCreatedAt()).thenReturn(LocalDateTime.of(2024, 1, 1, 0, 0));
        List<UsageService.VideoTaskRow> videoRows = new ArrayList<>();
        videoRows.add(r);
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(videoRows);
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(new ArrayList<>());

        List<UsageService.DailyUsage> result = usageService.byDay(7, null, "");

        assertEquals(1, result.size());
        assertEquals(LocalDate.of(2024, 1, 1), result.get(0).date());
        assertEquals(5L, result.get(0).tokens());
        assertEquals(1L, result.get(0).videoCount());
    }

    // ⑨b byDay(7,"",null) 步骤行 provider 空串不过滤：L183 缺失臂 provider=""
    @Test
    void byDayStepLoop_providerEmptyString_doesNotFilter() {
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(new ArrayList<>());
        UsageService.AgentStepRow r = org.mockito.Mockito.mock(UsageService.AgentStepRow.class);
        when(r.getAgentLabel()).thenReturn(AgentType.SCRIPT);
        when(r.getTokensUsed()).thenReturn(3L);
        when(r.getCostCents()).thenReturn(1L);
        when(r.getCreatedAt()).thenReturn(LocalDateTime.of(2024, 1, 2, 0, 0));
        List<UsageService.AgentStepRow> stepRows = new ArrayList<>();
        stepRows.add(r);
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(stepRows);

        List<UsageService.DailyUsage> result = usageService.byDay(7, "", null);

        assertEquals(1, result.size());
        assertEquals(3L, result.get(0).tokens());
        assertEquals(1L, result.get(0).stepCount());
    }

    // ⑨c byDay(7,null,"") 步骤行 model 空串不过滤：L187 缺失臂 model=""
    @Test
    void byDayStepLoop_modelEmptyString_doesNotFilter() {
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(new ArrayList<>());
        UsageService.AgentStepRow r = org.mockito.Mockito.mock(UsageService.AgentStepRow.class);
        when(r.getAgentLabel()).thenReturn(AgentType.SCRIPT);
        when(r.getTokensUsed()).thenReturn(3L);
        when(r.getCostCents()).thenReturn(1L);
        when(r.getCreatedAt()).thenReturn(LocalDateTime.of(2024, 1, 3, 0, 0));
        List<UsageService.AgentStepRow> stepRows = new ArrayList<>();
        stepRows.add(r);
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(stepRows);

        List<UsageService.DailyUsage> result = usageService.byDay(7, null, "");

        assertEquals(1, result.size());
        assertEquals(3L, result.get(0).tokens());
    }

    // ⑩ byDay 步骤行 getTokensUsed()=null 且 getCostCents()=null：L191、L192 缺失臂
    @Test
    void byDayStepLoop_nullTokensAndCost_useZero() {
        when(videoTaskRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(new ArrayList<>());
        UsageService.AgentStepRow r = org.mockito.Mockito.mock(UsageService.AgentStepRow.class);
        when(r.getAgentLabel()).thenReturn(AgentType.SCRIPT);
        when(r.getTokensUsed()).thenReturn(null);
        when(r.getCostCents()).thenReturn(null);
        when(r.getCreatedAt()).thenReturn(LocalDateTime.of(2024, 1, 4, 0, 0));
        List<UsageService.AgentStepRow> stepRows = new ArrayList<>();
        stepRows.add(r);
        when(agentStepRepository.findForDailyUsage(any(LocalDateTime.class))).thenReturn(stepRows);

        List<UsageService.DailyUsage> result = usageService.byDay(7, null, null);

        assertEquals(1, result.size());
        assertEquals(0L, result.get(0).tokens());
        assertEquals(0L, result.get(0).costCents());
        assertEquals(1L, result.get(0).stepCount());
    }
}
