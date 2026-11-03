package com.dramafactory.service.video;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.stereotype.Service;

/**
 * 视频提供方评分服务。
 *
 * <p>在路由之前对候选提供方进行多维度加权评分，输出可解释的排序结果。
 * 纯计算逻辑，不依赖任何外部组件，也不调用路由。</p>
 */
@Service
public class ProviderScoringService {

    private static final double WEIGHT_TASK_FIT = 0.30;
    private static final double WEIGHT_QUALITY = 0.20;
    private static final double WEIGHT_CONTROL = 0.15;
    private static final double WEIGHT_RELIABILITY = 0.15;
    private static final double WEIGHT_COST_EFFICIENCY = 0.10;
    private static final double WEIGHT_LATENCY = 0.05;
    private static final double WEIGHT_CONTINUITY = 0.05;

    private static final double DEFAULT_TASK_FIT = 0.3;
    private static final double DEFAULT_CONTROL = 0.3;
    private static final double DEFAULT_CONTINUITY_EMPTY = 0.5;
    private static final double CONTINUITY_MATCH = 0.9;
    private static final double CONTINUITY_MISS = 0.4;

    private static final double CONTROL_DENOMINATOR_FACTOR = 0.5;

    private static final double MOTION_PENALTY_FACTOR = 0.2;
    private static final double LOW_TASK_FIT_THRESHOLD = 0.3;

    private static final Set<String> MOTION_TOKENS = Set.of("video", "motion", "clip", "tvc", "film");

    private static final Map<String, Double> CONTROL_WEIGHTS = buildControlWeights();

    private static Map<String, Double> buildControlWeights() {
        Map<String, Double> map = new LinkedHashMap<>();
        map.put("referenceImage", 2.0);
        map.put("cameraControl", 1.5);
        map.put("styleTransfer", 1.5);
        map.put("img2img", 1.3);
        map.put("negativePrompt", 1.0);
        map.put("aspectRatio", 0.7);
        map.put("seed", 0.5);
        return Map.copyOf(map);
    }

    /** 延迟等级。 */
    public enum LatencyClass {
        FAST, MEDIUM, SLOW
    }

    /**
     * 候选提供方。
     *
     * @param name                 提供方名称
     * @param bestFor              擅长领域关键词集合
     * @param estimatedCostUsd     预估成本（美元）
     * @param qualityScore         质量分 0-1
     * @param reliabilityScore     可靠性分 0-1
     * @param controlFeatures      可控特性集合
     * @param latencyClass         延迟等级
     * @param productionStability  是否生产级稳定
     */
    public record ProviderCandidate(
            String name,
            Set<String> bestFor,
            double estimatedCostUsd,
            double qualityScore,
            double reliabilityScore,
            Set<String> controlFeatures,
            LatencyClass latencyClass,
            boolean productionStability) {

        public ProviderCandidate {
            bestFor = bestFor == null ? Set.of() : Set.copyOf(bestFor);
            controlFeatures = controlFeatures == null ? Set.of() : Set.copyOf(controlFeatures);
            latencyClass = latencyClass == null ? LatencyClass.MEDIUM : latencyClass;
        }
    }

    /**
     * 任务上下文。
     *
     * @param intent                任务意图描述
     * @param styleKeywords         风格关键词集合
     * @param budgetCapUsd          预算上限，可为空
     * @param budgetRemainingUsd    剩余预算，可为空
     * @param qualityRequirement    质量要求 0-1
     * @param lockedProviders       已锁定提供方集合
     * @param motionRequired        是否需要动态镜头
     * @param assetType             资产类型
     */
    public record TaskContext(
            String intent,
            Set<String> styleKeywords,
            Double budgetCapUsd,
            Double budgetRemainingUsd,
            double qualityRequirement,
            Set<String> lockedProviders,
            boolean motionRequired,
            String assetType) {

        public TaskContext {
            styleKeywords = styleKeywords == null ? Set.of() : Set.copyOf(styleKeywords);
            lockedProviders = lockedProviders == null ? Set.of() : Set.copyOf(lockedProviders);
        }
    }

    /**
     * 已评分的提供方。
     *
     * @param providerName   提供方名称
     * @param weightedScore  加权总分
     * @param dimensions     各维度得分
     * @param reasons        可解释原因
     */
    public record ScoredProvider(
            String providerName,
            double weightedScore,
            Map<String, Double> dimensions,
            List<String> reasons) {

        public ScoredProvider {
            dimensions = dimensions == null ? Map.of() : Map.copyOf(dimensions);
            reasons = reasons == null ? List.of() : List.copyOf(reasons);
        }
    }

    /**
     * 对候选提供方进行加权评分并降序排序。
     *
     * @param candidates 候选列表，可为空
     * @param context    任务上下文，字段可为空
     * @return 排序后的评分结果，空输入返回空列表
     */
    public List<ScoredProvider> rank(List<ProviderCandidate> candidates, TaskContext context) {
        if (candidates == null || candidates.isEmpty()) {
            return List.of();
        }
        TaskContext safeContext = context == null
                ? new TaskContext("", Set.of(), null, null, 0.0, Set.of(), false, null)
                : context;

        List<ScoredProvider> scored = new ArrayList<>(candidates.size());
        for (ProviderCandidate candidate : candidates) {
            if (candidate == null) {
                continue;
            }
            scored.add(score(candidate, safeContext));
        }

        scored.sort(Comparator.comparingDouble(ScoredProvider::weightedScore).reversed());
        return scored;
    }

    private ScoredProvider score(ProviderCandidate candidate, TaskContext context) {
        double taskFit = clamp(computeTaskFit(candidate, context));
        double quality = clamp(computeQuality(candidate));
        double control = clamp(computeControl(candidate));
        double reliability = clamp(candidate.reliabilityScore());
        double costEfficiency = clamp(computeCostEfficiency(candidate, context));
        double latency = computeLatency(candidate.latencyClass());
        double continuity = clamp(computeContinuity(candidate, context));

        Map<String, Double> dimensions = new LinkedHashMap<>();
        dimensions.put("taskFit", taskFit);
        dimensions.put("quality", quality);
        dimensions.put("control", control);
        dimensions.put("reliability", reliability);
        dimensions.put("costEfficiency", costEfficiency);
        dimensions.put("latency", latency);
        dimensions.put("continuity", continuity);

        double weighted = taskFit * WEIGHT_TASK_FIT
                + quality * WEIGHT_QUALITY
                + control * WEIGHT_CONTROL
                + reliability * WEIGHT_RELIABILITY
                + costEfficiency * WEIGHT_COST_EFFICIENCY
                + latency * WEIGHT_LATENCY
                + continuity * WEIGHT_CONTINUITY;
        weighted = round4(weighted);

        List<String> reasons = buildReasons(dimensions, taskFit, costEfficiency);

        return new ScoredProvider(candidate.name(), weighted, dimensions, reasons);
    }

    private double computeTaskFit(ProviderCandidate candidate, TaskContext context) {
        Set<String> bestFor = candidate.bestFor();
        if (bestFor.isEmpty()) {
            return DEFAULT_TASK_FIT;
        }
        Set<String> intentTokens = new HashSet<>();
        intentTokens.addAll(tokenize(context.intent()));
        intentTokens.addAll(tokenizeSet(context.styleKeywords()));
        if (intentTokens.isEmpty()) {
            return DEFAULT_TASK_FIT;
        }
        Set<String> bestForTokens = tokenizeSet(bestFor);
        if (bestForTokens.isEmpty()) {
            return DEFAULT_TASK_FIT;
        }
        int overlap = 0;
        for (String token : intentTokens) {
            if (bestForTokens.contains(token)) {
                overlap++;
            }
        }
        double coefficient = (double) overlap / Math.min(intentTokens.size(), bestForTokens.size());
        if (context.motionRequired() && "video".equals(context.assetType())) {
            boolean hasMotion = false;
            for (String token : bestForTokens) {
                if (MOTION_TOKENS.contains(token)) {
                    hasMotion = true;
                    break;
                }
            }
            if (!hasMotion) {
                coefficient *= MOTION_PENALTY_FACTOR;
            }
        }
        return coefficient;
    }

    private double computeQuality(ProviderCandidate candidate) {
        double base = clamp(candidate.qualityScore());
        if (candidate.productionStability()) {
            base = Math.min(1.0, base + 0.05);
        }
        return base;
    }

    private double computeControl(ProviderCandidate candidate) {
        Set<String> features = candidate.controlFeatures();
        if (features.isEmpty()) {
            return DEFAULT_CONTROL;
        }
        double earned = 0.0;
        double totalWeight = 0.0;
        for (Map.Entry<String, Double> entry : CONTROL_WEIGHTS.entrySet()) {
            totalWeight += entry.getValue();
            if (features.contains(entry.getKey())) {
                earned += entry.getValue();
            }
        }
        if (totalWeight <= 0.0) {
            return DEFAULT_CONTROL;
        }
        return Math.min(1.0, earned / (totalWeight * CONTROL_DENOMINATOR_FACTOR));
    }

    private double computeCostEfficiency(ProviderCandidate candidate, TaskContext context) {
        double cost = candidate.estimatedCostUsd();
        if (cost <= 0.0) {
            return 1.0;
        }
        if (context.budgetCapUsd() != null && cost > context.budgetCapUsd()) {
            return 0.0;
        }
        Double remaining = context.budgetRemainingUsd();
        if (remaining != null) {
            if (remaining <= 0.0) {
                return 0.0;
            }
            double ratio = cost / remaining;
            if (ratio > 0.5) {
                return 0.1;
            }
            if (ratio > 0.2) {
                return 0.5;
            }
            return 0.8;
        }
        if (cost < 0.05) {
            return 0.9;
        }
        if (cost < 0.2) {
            return 0.7;
        }
        if (cost < 1.0) {
            return 0.5;
        }
        return 0.3;
    }

    private double computeLatency(LatencyClass latencyClass) {
        return switch (latencyClass) {
            case FAST -> 1.0;
            case MEDIUM -> 0.6;
            case SLOW -> 0.3;
        };
    }

    private double computeContinuity(ProviderCandidate candidate, TaskContext context) {
        Set<String> locked = context.lockedProviders();
        if (locked.isEmpty()) {
            return DEFAULT_CONTINUITY_EMPTY;
        }
        if (locked.contains(candidate.name())) {
            return CONTINUITY_MATCH;
        }
        return CONTINUITY_MISS;
    }

    private List<String> buildReasons(Map<String, Double> dimensions, double taskFit, double costEfficiency) {
        Map<String, Double> weightByKey = new LinkedHashMap<>();
        weightByKey.put("taskFit", WEIGHT_TASK_FIT);
        weightByKey.put("quality", WEIGHT_QUALITY);
        weightByKey.put("control", WEIGHT_CONTROL);
        weightByKey.put("reliability", WEIGHT_RELIABILITY);
        weightByKey.put("costEfficiency", WEIGHT_COST_EFFICIENCY);
        weightByKey.put("latency", WEIGHT_LATENCY);
        weightByKey.put("continuity", WEIGHT_CONTINUITY);

        Set<String> topKeys = new TreeSet<>(Comparator
                .comparingDouble((String key) -> dimensions.getOrDefault(key, 0.0) * weightByKey.getOrDefault(key, 0.0))
                .reversed()
                .thenComparing(Comparator.naturalOrder()));

        List<Map.Entry<String, Double>> entries = new ArrayList<>(weightByKey.entrySet());
        entries.sort((a, b) -> {
            double ca = dimensions.getOrDefault(a.getKey(), 0.0) * a.getValue();
            double cb = dimensions.getOrDefault(b.getKey(), 0.0) * b.getValue();
            int cmp = Double.compare(cb, ca);
            if (cmp != 0) {
                return cmp;
            }
            return a.getKey().compareTo(b.getKey());
        });

        List<String> reasons = new ArrayList<>();
        int limit = Math.min(3, entries.size());
        for (int i = 0; i < limit; i++) {
            Map.Entry<String, Double> entry = entries.get(i);
            double value = dimensions.getOrDefault(entry.getKey(), 0.0);
            reasons.add(String.format(Locale.ROOT, "%s=%.2f (权重%.2f)", entry.getKey(), value, entry.getValue()));
        }
        if (costEfficiency == 0.0) {
            reasons.add("超出预算上限");
        }
        if (taskFit < LOW_TASK_FIT_THRESHOLD) {
            reasons.add("任务匹配度低");
        }
        return reasons;
    }

    private Set<String> tokenize(String text) {
        if (text == null || text.isEmpty()) {
            return Set.of();
        }
        String[] parts = text.toLowerCase(Locale.ROOT).split("[^a-z0-9]+");
        Set<String> tokens = new HashSet<>();
        for (String part : parts) {
            if (!part.isEmpty()) {
                tokens.add(part);
            }
        }
        return tokens;
    }

    private Set<String> tokenizeSet(Set<String> values) {
        if (values == null || values.isEmpty()) {
            return Set.of();
        }
        Set<String> tokens = new HashSet<>();
        for (String value : values) {
            tokens.addAll(tokenize(value));
        }
        return tokens;
    }

    private double clamp(double value) {
        if (value < 0.0) {
            return 0.0;
        }
        if (value > 1.0) {
            return 1.0;
        }
        return value;
    }

    private double round4(double value) {
        return Math.round(value * 10000.0) / 10000.0;
    }
}
