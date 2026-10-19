
package com.dramafactory.service;

import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.VideoTaskRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.data.domain.PageRequest;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Token / 成本用量统计聚合服务。
 * 所有聚合均基于真实实体字段，空值不参与求和；全空或空表时返回 null 或空集合。
 */
@Service
public class UsageService {

    /** "不限时间"查询的下界：LocalDateTime.MIN 超出 H2 TIMESTAMP 可比范围会导致查询返回空，改用 1970 纪元。 */
    private static final java.time.LocalDateTime TIME_BEGIN = java.time.LocalDateTime.of(1970, 1, 1, 0, 0);

    private static final Logger log = LoggerFactory.getLogger(UsageService.class);

    private static final int DEFAULT_DAYS = 30;
    private static final int DEFAULT_RUN_LIMIT = 20;
    private static final int GOAL_MAX_LENGTH = 30;

    private final VideoTaskRepository videoTaskRepository;
    private final AgentStepRepository agentStepRepository;
    private final RunRepository runRepository;

    public UsageService(VideoTaskRepository videoTaskRepository,
                        AgentStepRepository agentStepRepository,
                        RunRepository runRepository) {
        this.videoTaskRepository = videoTaskRepository;
        this.agentStepRepository = agentStepRepository;
        this.runRepository = runRepository;
    }

    /**
     * 总量汇总：tokensTotal / costCentsTotal 为 VideoTask 与 AgentStep 非空字段之和，全空则为 null。
     * taskCount 为 VideoTask 总数，runCount 为 Run 总数。
     */
    @Transactional(readOnly = true)
    public UsageSummary summary(String provider, String model, int days) {
        boolean noFilter = (provider == null || provider.isEmpty()) && (model == null || model.isEmpty()) && days <= 0;
        if (noFilter) {
            Long tokens = sumNullable(videoTaskRepository.sumTokensUsed(), agentStepRepository.sumTokensUsed());
            Long cost = sumNullable(videoTaskRepository.sumCostCents(), agentStepRepository.sumCostCents());
            long taskCount = videoTaskRepository.count();
            long runCount = runRepository.count();
            long stepCount = agentStepRepository.count();
            long requestCount = taskCount + stepCount;
            Long promptTotal = sumNullable(videoTaskRepository.sumPromptTokens(), agentStepRepository.sumPromptTokens());
            Long completionTotal = sumNullable(videoTaskRepository.sumCompletionTokens(), agentStepRepository.sumCompletionTokens());
            Long cachedTotal = sumNullable(videoTaskRepository.sumCachedTokens(), agentStepRepository.sumCachedTokens());
            return new UsageSummary(tokens, cost, taskCount, runCount, stepCount, requestCount,
                    promptTotal, completionTotal, cachedTotal, cacheHitRate(cachedTotal, promptTotal, completionTotal));
        }
        LocalDateTime from = days > 0 ? LocalDateTime.now().minusDays(days) : null;
        List<RequestVideoRow> videoRows = videoTaskRepository.findForRequests(from != null ? from : TIME_BEGIN);
        List<RequestStepRow> stepRows = agentStepRepository.findForRequests(from != null ? from : TIME_BEGIN);
        Long tokens = null;
        Long cost = null;
        long taskCount = 0;
        long stepCount = 0;
        for (RequestVideoRow r : videoRows) {
            if (provider != null && !provider.isEmpty() && !provider.equals(r.getProvider())) {
                continue;
            }
            if (model != null && !model.isEmpty() && !model.equals(r.getModelUsed())) {
                continue;
            }
            tokens = sumNullable(tokens, r.getTokensUsed());
            cost = sumNullable(cost, r.getCostCents());
            taskCount++;
        }
        for (RequestStepRow r : stepRows) {
            if (provider != null && !provider.isEmpty()) {
                continue;
            }
            String label = r.getAgentLabel() != null ? r.getAgentLabel().getLabel() : null;
            if (model != null && !model.isEmpty() && !model.equals(label)) {
                continue;
            }
            tokens = sumNullable(tokens, r.getTokensUsed());
            cost = sumNullable(cost, r.getCostCents());
            stepCount++;
        }
        long requestCount = taskCount + stepCount;
        return new UsageSummary(tokens, cost, taskCount, 0L, stepCount, requestCount,
                null, null, null, 0.0);
    }

    @Transactional(readOnly = true)
    public List<RequestUsage> requests(int limit, String provider, String model, int days) {
        LocalDateTime from = days > 0 ? LocalDateTime.now().minusDays(days) : TIME_BEGIN;
        List<RequestVideoRow> videoRows = videoTaskRepository.findForRequests(from);
        List<RequestStepRow> stepRows = agentStepRepository.findForRequests(from);
        List<RequestUsage> result = new ArrayList<>();
        for (RequestVideoRow r : videoRows) {
            if (r.getModelUsed() == null) {
                continue;
            }
            if (provider != null && !provider.isEmpty() && !provider.equals(r.getProvider())) {
                continue;
            }
            if (model != null && !model.isEmpty() && !model.equals(r.getModelUsed())) {
                continue;
            }
            String status = r.getStatus() != null ? String.valueOf(r.getStatus()) : null;
            result.add(new RequestUsage(r.getId(), "VIDEO_TASK", r.getCreatedAt(), r.getProvider(),
                    r.getModelUsed(), r.getTokensUsed(), r.getPromptTokens(), r.getCompletionTokens(), r.getCachedTokens(),
                    r.getCostCents(), r.getCostEstimated(),
                    null, status));
        }
        for (RequestStepRow r : stepRows) {
            if (provider != null && !provider.isEmpty()) {
                continue;
            }
            String label = r.getAgentLabel() != null ? r.getAgentLabel().getLabel() : null;
            if (model != null && !model.isEmpty() && !model.equals(label)) {
                continue;
            }
            String status = r.getStatus() != null ? String.valueOf(r.getStatus()) : null;
            result.add(new RequestUsage(r.getId(), "AGENT_STEP", r.getCreatedAt(), null,
                    label, r.getTokensUsed(), r.getPromptTokens(), r.getCompletionTokens(), r.getCachedTokens(),
                    r.getCostCents(), r.getCostEstimated(),
                    r.getLatencyMs(), status));
        }
        result.sort((a, b) -> {
            LocalDateTime ta = a.time();
            LocalDateTime tb = b.time();
            if (ta == null && tb == null) {
                return 0;
            }
            if (ta == null) {
                return 1;
            }
            if (tb == null) {
                return -1;
            }
            return tb.compareTo(ta);
        });
        if (limit > 0 && result.size() > limit) {
            return result.subList(0, limit);
        }
        return result;
    }

    @Transactional(readOnly = true)
    public List<DailyUsage> byDay(int days, String provider, String model) {
        int effectiveDays = days <= 0 ? DEFAULT_DAYS : days;
        LocalDateTime from = LocalDateTime.now().minusDays(effectiveDays);
        List<VideoTaskRow> videoRows = videoTaskRepository.findForDailyUsage(from);
        List<AgentStepRow> stepRows = agentStepRepository.findForDailyUsage(from);
        Map<LocalDate, Long> tokenMap = new TreeMap<>();
        Map<LocalDate, Long> costMap = new TreeMap<>();
        Map<LocalDate, Long> videoCountMap = new TreeMap<>();
        Map<LocalDate, Long> stepCountMap = new TreeMap<>();
        for (VideoTaskRow r : videoRows) {
            if (provider != null && !provider.isEmpty() && !provider.equals(r.getProvider())) {
                continue;
            }
            if (model != null && !model.isEmpty() && !model.equals(r.getModelUsed())) {
                continue;
            }
            LocalDate d = r.getCreatedAt().toLocalDate();
            tokenMap.merge(d, r.getTokensUsed() != null ? r.getTokensUsed() : 0L, Long::sum);
            costMap.merge(d, r.getCostCents() != null ? r.getCostCents() : 0L, Long::sum);
            videoCountMap.merge(d, 1L, Long::sum);
        }
        for (AgentStepRow r : stepRows) {
            // AgentStep 无 provider 字段，无法归属到视频供应商；按 provider 过滤时整体跳过（有意设计，非遗漏）
            if (provider != null && !provider.isEmpty()) {
                continue;
            }
            String label = r.getAgentLabel() != null ? r.getAgentLabel().getLabel() : null;
            if (model != null && !model.isEmpty() && !model.equals(label)) {
                continue;
            }
            LocalDate d = r.getCreatedAt().toLocalDate();
            tokenMap.merge(d, r.getTokensUsed() != null ? r.getTokensUsed() : 0L, Long::sum);
            costMap.merge(d, r.getCostCents() != null ? r.getCostCents() : 0L, Long::sum);
            stepCountMap.merge(d, 1L, Long::sum);
        }
        Set<LocalDate> dates = new TreeSet<>();
        dates.addAll(tokenMap.keySet());
        dates.addAll(costMap.keySet());
        dates.addAll(videoCountMap.keySet());
        dates.addAll(stepCountMap.keySet());
        List<DailyUsage> result = new ArrayList<>();
        for (LocalDate d : dates) {
            result.add(new DailyUsage(d, tokenMap.get(d), costMap.get(d),
                    videoCountMap.getOrDefault(d, 0L), stepCountMap.getOrDefault(d, 0L)));
        }
        return result;
    }

    @Transactional(readOnly = true)
    public FilterOptions filters() {
        List<String> providers = new ArrayList<>(new TreeSet<>(videoTaskRepository.findDistinctProviders()));
        Set<String> modelSet = new TreeSet<>();
        modelSet.addAll(videoTaskRepository.findDistinctModels());
        for (AgentType t : agentStepRepository.findDistinctAgentTypes()) {
            if (t != null) {
                modelSet.add(t.getLabel());
            }
        }
        return new FilterOptions(providers, new ArrayList<>(modelSet));
    }

    public UsageSummary summary() {
        Long videoTokens = videoTaskRepository.sumTokensUsed();
        Long agentTokens = agentStepRepository.sumTokensUsed();
        Long tokensTotal = sumNullable(videoTokens, agentTokens);

        Long videoCost = videoTaskRepository.sumCostCents();
        Long agentCost = agentStepRepository.sumCostCents();
        Long costCentsTotal = sumNullable(videoCost, agentCost);

        long taskCount = videoTaskRepository.count();
        long runCount = runRepository.count();
        long stepCount = agentStepRepository.count();
        long requestCount = taskCount + stepCount;

        Long promptTotal = sumNullable(videoTaskRepository.sumPromptTokens(), agentStepRepository.sumPromptTokens());
        Long completionTotal = sumNullable(videoTaskRepository.sumCompletionTokens(), agentStepRepository.sumCompletionTokens());
        Long cachedTotal = sumNullable(videoTaskRepository.sumCachedTokens(), agentStepRepository.sumCachedTokens());
        log.debug("usage summary: tokensTotal={}, costCentsTotal={}, taskCount={}, runCount={}, stepCount={}, requestCount={}, promptTotal={}, completionTotal={}, cachedTotal={}",
                tokensTotal, costCentsTotal, taskCount, runCount, stepCount, requestCount, promptTotal, completionTotal, cachedTotal);
        return new UsageSummary(tokensTotal, costCentsTotal, taskCount, runCount, stepCount, requestCount,
                promptTotal, completionTotal, cachedTotal, cacheHitRate(cachedTotal, promptTotal, completionTotal));
    }

    /**
     * 按模型/Agent 类型聚合。
     * - VideoTask 按 modelUsed 分组，求和 tokensUsed / costCents，taskCount 为该组 VideoTask 数。
     * - AgentStep 按 agentType.getLabel() 分组，求和 tokensUsed / costCents，taskCount 为该组 step 数。
     */
    @Transactional(readOnly = true)
    public List<ModelUsage> byModel() {
        Map<String, ModelAccumulator> grouped = new LinkedHashMap<>();

        // VideoTask 按 modelUsed 分组
        List<VideoTaskRow> videoRows = videoTaskRepository.findAllForModelUsage();
        for (VideoTaskRow row : videoRows) {
            String model = row.getModelUsed() == null ? null : row.getModelUsed();
            if (model == null) {
                // 无模型名不参与聚合分组（避免用假 key 冒充）
                continue;
            }
            ModelAccumulator acc = grouped.computeIfAbsent(model, k -> new ModelAccumulator(k));
            acc.tokens = sumNullable(acc.tokens, row.getTokensUsed());
            acc.costCents = sumNullable(acc.costCents, row.getCostCents());
            acc.taskCount += 1;
        }

        // AgentStep 按 agentType.getLabel() 分组
        List<AgentStepRow> stepRows = agentStepRepository.findAllForModelUsage();
        for (AgentStepRow row : stepRows) {
            if (row.getAgentLabel() == null) {
                continue;
            }
            String label = row.getAgentLabel().getLabel();
            ModelAccumulator acc = grouped.computeIfAbsent(label, k -> new ModelAccumulator(k));
            acc.tokens = sumNullable(acc.tokens, row.getTokensUsed());
            acc.costCents = sumNullable(acc.costCents, row.getCostCents());
            acc.taskCount += 1;
        }

        List<ModelUsage> result = new ArrayList<>(grouped.size());
        for (ModelAccumulator acc : grouped.values()) {
            result.add(new ModelUsage(acc.model, acc.tokens, acc.costCents, acc.taskCount));
        }
        log.debug("usage byModel: {} groups", result.size());
        return result;
    }

    /** 按视频供应商聚合用量。AgentStep 无供应商概念，不参与。 */
    @Transactional(readOnly = true)
    public List<ProviderUsage> byProvider() {
        Map<String, ProviderAccumulator> grouped = new LinkedHashMap<>();

        List<VideoTaskRow> videoRows = videoTaskRepository.findAllForModelUsage();
        for (VideoTaskRow row : videoRows) {
            String provider = row.getProvider();
            if (provider == null || provider.isEmpty()) {
                // 无供应商名不参与聚合分组
                continue;
            }
            ProviderAccumulator acc = grouped.computeIfAbsent(provider, k -> new ProviderAccumulator(k));
            acc.tokens = sumNullable(acc.tokens, row.getTokensUsed());
            acc.costCents = sumNullable(acc.costCents, row.getCostCents());
            acc.taskCount += 1;
        }

        List<ProviderUsage> result = new ArrayList<>(grouped.size());
        for (ProviderAccumulator acc : grouped.values()) {
            result.add(new ProviderUsage(acc.provider, acc.tokens, acc.costCents, acc.taskCount));
        }
        result.sort(Comparator.comparing(ProviderUsage::provider));
        log.debug("usage byProvider: {} groups", result.size());
        return result;
    }

    /**
     * 按天聚合近 N 天（默认 30）数据，VideoTask 与 AgentStep 合并到同一日期。
     */
    @Transactional(readOnly = true)
    public List<DailyUsage> byDay(int days) {
        return byDay(days, null, null);
    }
    /**
     * 按 Run 聚合，按 createdAt 倒序，默认取最近 20 条。
     * tokens 优先使用 Run.totalTokens，为空则回退到该 Run 下 AgentStep.tokensUsed 之和；
     * costCents 优先使用 Run.totalCostCents，为空则回退到 AgentStep.costCents 之和。
     */
    @Transactional(readOnly = true)
    public List<RunUsage> byRun(int limit) {
        int effectiveLimit = limit <= 0 ? DEFAULT_RUN_LIMIT : limit;
        List<RunRow> runs = runRepository.findAllByOrderByCreatedAtDesc(PageRequest.of(0, effectiveLimit));

        List<RunUsage> result = new ArrayList<>(runs.size());
        for (RunRow run : runs) {
            Long tokens = run.getTotalTokens();
            if (tokens == null) {
                tokens = agentStepRepository.sumTokensUsedByRunId(run.getId());
            }
            Long costCents = run.getTotalCostCents();
            if (costCents == null) {
                costCents = agentStepRepository.sumCostCentsByRunId(run.getId());
            }
            String goal = run.getGoal();
            if (goal != null && goal.length() > GOAL_MAX_LENGTH) {
                goal = goal.substring(0, GOAL_MAX_LENGTH);
            }
            result.add(new RunUsage(run.getId(), goal, tokens, costCents, run.getCreatedAt()));
        }
        log.debug("usage byRun: limit={}, {} runs", effectiveLimit, result.size());
        return result;
    }

    /** 非空求和：两者都为 null 返回 null，否则返回有效值之和。 */
    private static Double cacheHitRate(Long cached, Long prompt, Long completion) {
        long c = cached == null ? 0L : cached;
        long p = prompt == null ? 0L : prompt;
        long co = completion == null ? 0L : completion;
        long total = c + p + co;
        if (total <= 0) {
            return 0.0;
        }
        return (double) c / total;
    }

    private static Long sumNullable(Long a, Long b) {
        if (a == null && b == null) {
            return null;
        }
        long va = a == null ? 0L : a;
        long vb = b == null ? 0L : b;
        return va + vb;
    }

    // ==== 返回 DTO（service 层，供 controller 使用） ====

    /** 总量汇总。 */
    public record UsageSummary(Long tokensTotal, Long costCentsTotal, long taskCount, long runCount, long stepCount, long requestCount,
                               Long promptTokensTotal, Long completionTokensTotal, Long cachedTokensTotal, Double cacheHitRate) {}

    /** 按模型/Agent 类型聚合。 */
    public record ModelUsage(String model, Long tokens, Long costCents, long taskCount) {}

    /** 按视频供应商聚合。 */
    public record ProviderUsage(String provider, Long tokens, Long costCents, long taskCount) {}

    /** 按天聚合。 */
    public record DailyUsage(LocalDate date, Long tokens, Long costCents, long videoCount, long stepCount) {}

    /** 按 Run 聚合。 */
    public record RunUsage(Long runId, String goal, Long tokens, Long costCents, LocalDateTime createdAt) {}

public record RequestUsage(Long id, String kind, LocalDateTime time, String provider, String model,
                           Long tokensUsed, Long promptTokens, Long completionTokens, Long cachedTokens,
                           Long costCents, Boolean costEstimated,
                           Long latencyMs, String status) {}

public record FilterOptions(List<String> providers, List<String> models) {}

    // ==== 内部累加器 ====

    private static final class ModelAccumulator {
        final String model;
        Long tokens;
        Long costCents;
        long taskCount;

        ModelAccumulator(String model) {
            this.model = model;
        }
    }

    private static final class ProviderAccumulator {
        final String provider;
        Long tokens;
        Long costCents;
        long taskCount;

        ProviderAccumulator(String provider) {
            this.provider = provider;
        }
    }

    private static final class DailyAccumulator {
        final LocalDate date;
        Long tokens;
        Long costCents;

        DailyAccumulator(LocalDate date) {
            this.date = date;
        }
    }

    // ==== 查询投影接口（供 repository 使用） ====

    /** VideoTask 聚合用投影。 */
    public interface VideoTaskRow {
        String getModelUsed();
        Long getTokensUsed();
        Long getCostCents();
        LocalDateTime getCreatedAt();
        String getProvider();
    }

    /** VideoTask 请求明细投影。 */
    public interface RequestVideoRow {
        Long getId();
        String getProvider();
        String getModelUsed();
        Long getTokensUsed();
        Long getPromptTokens();
        Long getCompletionTokens();
        Long getCachedTokens();
        Long getCostCents();
        Boolean getCostEstimated();
        VideoTaskStatus getStatus();
        LocalDateTime getCreatedAt();
    }

    /** AgentStep 聚合用投影。 */
    public interface AgentStepRow {
        AgentType getAgentLabel();
        Long getTokensUsed();
        Long getCostCents();
        LocalDateTime getCreatedAt();
    }

    /** AgentStep 请求明细投影。 */
    public interface RequestStepRow {
        Long getId();
        AgentType getAgentLabel();
        Long getTokensUsed();
        Long getPromptTokens();
        Long getCompletionTokens();
        Long getCachedTokens();
        Long getCostCents();
        Boolean getCostEstimated();
        Long getLatencyMs();
        AgentStepStatus getStatus();
        LocalDateTime getCreatedAt();
    }

    /** Run 聚合用投影。 */
    public interface RunRow {
        Long getId();
        String getGoal();
        Long getTotalTokens();
        Long getTotalCostCents();
        LocalDateTime getCreatedAt();
    }
}
