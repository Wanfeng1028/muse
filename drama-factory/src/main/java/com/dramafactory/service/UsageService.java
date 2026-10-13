
package com.dramafactory.service;

import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.model.AgentType;
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

/**
 * Token / 成本用量统计聚合服务。
 * 所有聚合均基于真实实体字段，空值不参与求和；全空或空表时返回 null 或空集合。
 */
@Service
public class UsageService {

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
    public UsageSummary summary() {
        Long videoTokens = videoTaskRepository.sumTokensUsed();
        Long agentTokens = agentStepRepository.sumTokensUsed();
        Long tokensTotal = sumNullable(videoTokens, agentTokens);

        Long videoCost = videoTaskRepository.sumCostCents();
        Long agentCost = agentStepRepository.sumCostCents();
        Long costCentsTotal = sumNullable(videoCost, agentCost);

        long taskCount = videoTaskRepository.count();
        long runCount = runRepository.count();

        log.debug("usage summary: tokensTotal={}, costCentsTotal={}, taskCount={}, runCount={}",
                tokensTotal, costCentsTotal, taskCount, runCount);
        return new UsageSummary(tokensTotal, costCentsTotal, taskCount, runCount);
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

    /**
     * 按天聚合近 N 天（默认 30）数据，VideoTask 与 AgentStep 合并到同一日期。
     */
    @Transactional(readOnly = true)
    public List<DailyUsage> byDay(int days) {
        int effectiveDays = days <= 0 ? DEFAULT_DAYS : days;
        LocalDate from = LocalDate.now().minusDays(effectiveDays - 1L);
        LocalDateTime fromTime = from.atStartOfDay();

        Map<LocalDate, DailyAccumulator> grouped = new LinkedHashMap<>();

        List<VideoTaskRow> videoRows = videoTaskRepository.findForDailyUsage(fromTime);
        for (VideoTaskRow row : videoRows) {
            LocalDateTime createdAt = row.getCreatedAt();
            if (createdAt == null) {
                continue;
            }
            LocalDate date = createdAt.toLocalDate();
            DailyAccumulator acc = grouped.computeIfAbsent(date, k -> new DailyAccumulator(k));
            acc.tokens = sumNullable(acc.tokens, row.getTokensUsed());
            acc.costCents = sumNullable(acc.costCents, row.getCostCents());
        }

        List<AgentStepRow> stepRows = agentStepRepository.findForDailyUsage(fromTime);
        for (AgentStepRow row : stepRows) {
            LocalDateTime createdAt = row.getCreatedAt();
            if (createdAt == null) {
                continue;
            }
            LocalDate date = createdAt.toLocalDate();
            DailyAccumulator acc = grouped.computeIfAbsent(date, k -> new DailyAccumulator(k));
            acc.tokens = sumNullable(acc.tokens, row.getTokensUsed());
            acc.costCents = sumNullable(acc.costCents, row.getCostCents());
        }

        List<DailyUsage> result = new ArrayList<>(grouped.size());
        for (DailyAccumulator acc : grouped.values()) {
            result.add(new DailyUsage(acc.date, acc.tokens, acc.costCents));
        }
        result.sort(Comparator.comparing(DailyUsage::date));
        log.debug("usage byDay: days={}, {} groups", effectiveDays, result.size());
        return result;
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
    public record UsageSummary(Long tokensTotal, Long costCentsTotal, long taskCount, long runCount) {}

    /** 按模型/Agent 类型聚合。 */
    public record ModelUsage(String model, Long tokens, Long costCents, long taskCount) {}

    /** 按天聚合。 */
    public record DailyUsage(LocalDate date, Long tokens, Long costCents) {}

    /** 按 Run 聚合。 */
    public record RunUsage(Long runId, String goal, Long tokens, Long costCents, LocalDateTime createdAt) {}

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
    }

    /** AgentStep 聚合用投影。 */
    public interface AgentStepRow {
        AgentType getAgentLabel();
        Long getTokensUsed();
        Long getCostCents();
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
