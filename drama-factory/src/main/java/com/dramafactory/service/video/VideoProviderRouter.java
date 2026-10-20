package com.dramafactory.service.video;

import com.dramafactory.billing.BillingProperties;
import com.dramafactory.billing.BudgetExceededException;
import com.dramafactory.billing.CostLedgerService;
import com.dramafactory.billing.ProviderCostEstimator;
import com.dramafactory.model.Shot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class VideoProviderRouter {

    private static final Logger log = LoggerFactory.getLogger(VideoProviderRouter.class);

    private static final List<String> DEFAULT_ORDER = List.of("agnes", "minimax", "novai", "doubao", "hyperframes", "htmlrender", "painted");
    private static final String MOCK = "mock";

    private final ApplicationContext applicationContext;
    private final Environment environment;
    private final ShotVideoRouter shotVideoRouter;
    private final ProviderDescriptorRegistry descriptorRegistry;


    private volatile LastFallback lastFallback;

    /**
     * 成本账本服务，计费关闭或未装配时为 null。
     */
    private final CostLedgerService costLedgerService;

    /**
     * 提供方成本估算器，计费关闭或未装配时为 null。
     */
    private final ProviderCostEstimator costEstimator;

    /**
     * 计费配置，计费关闭或未装配时为 null。
     */
    private final BillingProperties billingProperties;

    /**
     * 最近的路由决策日志，最多保留 50 条，超出时丢弃最旧记录。
     */
    private final Deque<RoutingDecision> decisionLog = new ArrayDeque<>();

    private static final int MAX_DECISION_LOG = 50;

    @org.springframework.beans.factory.annotation.Autowired
    public VideoProviderRouter(ApplicationContext applicationContext, Environment environment,
                               ShotVideoRouter shotVideoRouter, ProviderDescriptorRegistry descriptorRegistry,
                               CostLedgerService costLedgerService, ProviderCostEstimator costEstimator,
                               BillingProperties billingProperties) {
        this.applicationContext = applicationContext;
        this.environment = environment;
        this.shotVideoRouter = shotVideoRouter;
        this.descriptorRegistry = descriptorRegistry;
        this.costLedgerService = costLedgerService;
        this.costEstimator = costEstimator;
        this.billingProperties = billingProperties;
    }

    /**
     * 兼容构造器：不接入成本账本，计费视为关闭。
     */
    public VideoProviderRouter(ApplicationContext applicationContext, Environment environment,
                               ShotVideoRouter shotVideoRouter, ProviderDescriptorRegistry descriptorRegistry) {
        this(applicationContext, environment, shotVideoRouter, descriptorRegistry, null, null, null);
    }

    /**
     * 测试兼容构造器：descriptorRegistry 为 null 时 descriptor: 通道不可用。
     */
    public VideoProviderRouter(ApplicationContext applicationContext, Environment environment,
                               ShotVideoRouter shotVideoRouter) {
        this(applicationContext, environment, shotVideoRouter, null);
    }


    /**
     * 视频通道路由结果。
     *
     * @param providerName   最终提交成功的通道名
     * @param providerTaskId 通道返回的任务 id
     * @param fallbackReason 降级原因，首选通道成功时为 null
     * @param ledgerEntryId  成本账本条目 id，可为 null（计费关闭或未启用时）
     */
    public record RouteResult(String providerName, String providerTaskId, String fallbackReason, Long ledgerEntryId) {
    }

    public record LastFallback(String from, String to, String reason, LocalDateTime at) {
    }

    public LastFallback lastFallback() {
        return lastFallback;
    }

    public List<String> chain() {
        String preferred = environment.getProperty("drama.video.provider", "mock");
        if (preferred == null || preferred.isBlank()) {
            preferred = "mock";
        }
        if (MOCK.equals(preferred)) {
            return List.of(MOCK);
        }
        List<String> result = new ArrayList<>();
        result.add(preferred);
        for (String candidate : DEFAULT_ORDER) {
            if (!candidate.equals(preferred)) {
                result.add(candidate);
            }
        }
        return result;
    }

    /**
     * 按分镜决定通道链：分镜首选 → 全局 preferred → 默认顺序去重。
     */
    public List<String> chain(Shot shot) {
        String preferred = environment.getProperty("drama.video.provider", "mock");
        if (preferred == null || preferred.isBlank()) {
            preferred = "mock";
        }
        if (MOCK.equals(preferred)) {
            return List.of(MOCK);
        }
        String shotPreferred = null;
        if (shot != null && shotVideoRouter != null) {
            shotPreferred = shotVideoRouter.route(shot);
            if (shotPreferred != null && shotPreferred.isBlank()) {
                shotPreferred = null;
            }
        }
        List<String> result = new ArrayList<>();
        if (shotPreferred != null) {
            result.add(shotPreferred);
        }
        if (!preferred.equals(shotPreferred)) {
            result.add(preferred);
        }
        for (String candidate : DEFAULT_ORDER) {
            if (!candidate.equals(shotPreferred) && !candidate.equals(preferred)
                    && !result.contains(candidate)) {
                result.add(candidate);
            }
        }
        return result;
    }

    public VideoProvider providerFor(String name) {
        if (name != null && name.startsWith("descriptor:")) {
            if (descriptorRegistry == null) {
                throw new IllegalStateException("描述符 provider 注册表未装配");
            }
            return descriptorRegistry.buildProvider(name.substring("descriptor:".length()));
        }
        if ("agnes".equals(name)) {

            return applicationContext.getBean("agnesVideoProvider", VideoProvider.class);
        }
        if ("minimax".equals(name)) {
            return applicationContext.getBean("miniMaxH3VideoProvider", VideoProvider.class);
        }
        if ("comfyui".equals(name)) {
            return applicationContext.getBean("localH3VideoProvider", VideoProvider.class);
        }
        if ("local-h3".equals(name)) {
            return applicationContext.getBean("localH3VideoProvider", VideoProvider.class);
        }
        if ("qwen".equals(name)) {
            return applicationContext.getBean("qwenVideoProvider", VideoProvider.class);
        }
        if ("novai".equals(name)) {
            return applicationContext.getBean("novAiVideoProvider", VideoProvider.class);
        }
        if ("doubao".equals(name)) {
            return applicationContext.getBean("doubaoEmailVideoProvider", VideoProvider.class);
        }
        if ("hyperframes".equals(name)) {
            return applicationContext.getBean("hyperFramesVideoProvider", VideoProvider.class);
        }
        if ("painted".equals(name)) {
            return applicationContext.getBean("paintedAnimationVideoProvider", VideoProvider.class);
        }
        if ("htmlrender".equals(name)) {
            return applicationContext.getBean("htmlRenderVideoProvider", VideoProvider.class);
        }
        if ("mock".equals(name)) {
            return applicationContext.getBean("mockVideoProvider", VideoProvider.class);
        }
        throw new IllegalArgumentException("未知视频通道：" + name);
    }

    public RouteResult submit(Shot shot, int seconds) {
        Long projectId = extractProjectId(shot);
        boolean billingOn = billingEnabled();
        List<String> chain = chain(shot);
        List<String> failures = new ArrayList<>();
        for (int i = 0; i < chain.size(); i++) {
            String current = chain.get(i);
            Long entryId = null;
            if (billingOn) {
                double estimated = costEstimator.estimate(current, seconds);
                entryId = costLedgerService.recordEstimate(projectId, current, current, "video-generate", estimated,
                        "shotId=" + (shot == null ? "null" : String.valueOf(shot.getId()))
                                + ";seconds=" + seconds + ";估算值，提供方未上报真实费用");
                try {
                    costLedgerService.reserve(entryId, billingProperties.toBudgetPolicy());
                } catch (BudgetExceededException e) {
                    failures.add("预算超限(CAP)，跳过" + current);
                    log.warn("视频通道因预算超限跳过：{}", current);
                    continue;
                }
            }
            try {
                String providerTaskId = providerFor(current).submit(shot, seconds);
                if (i == 0) {
                    return new RouteResult(current, providerTaskId, null, entryId);
                }
                String from = chain.get(0);
                String reason = failures.isEmpty() ? null : failures.get(failures.size() - 1);
                log.warn("视频通道降级：{}→{}，原因={}", from, current, reason);
                lastFallback = new LastFallback(from, current, reason, LocalDateTime.now());
                return new RouteResult(current, providerTaskId, reason, entryId);
            } catch (RateLimitedException e) {
                safeRefund(entryId);
                String reason = "限流(429)，" + e.getRetryAfterSeconds() + "秒后可重试";
                failures.add(reason);
                log.warn("视频通道降级：{}→{}，原因={}", current, nextName(chain, i), reason);
            } catch (RuntimeException e) {
                safeRefund(entryId);
                String reason;
                String msg = e.getMessage();
                if (msg != null && msg.contains("超时")) {
                    reason = "调用超时";
                } else {
                    String truncated = msg == null ? "" : msg;
                    if (truncated.length() > 100) {
                        truncated = truncated.substring(0, 100);
                    }
                    reason = "提交异常：" + truncated;
                }
                failures.add(reason);
                log.warn("视频通道降级：{}→{}，原因={}", current, nextName(chain, i), reason);
            }
        }
        throw new RuntimeException("所有视频通道均失败：" + String.join("；", failures));
    }

    /**
     * 判断成本账本是否可用：配置开启且账本服务与估算器均已装配。
     */
    private boolean billingEnabled() {
        return billingProperties != null && billingProperties.isEnabled()
                && costLedgerService != null && costEstimator != null;
    }

    /**
     * 安全退款：账本条目为空时直接返回；退款异常只记告警，绝不向上抛出。
     */
    private void safeRefund(Long entryId) {
        if (entryId == null) {
            return;
        }
        try {
            costLedgerService.refund(entryId);
        } catch (RuntimeException e) {
            log.warn("账本退款失败，不影响主流程：{}", e.getMessage());
        }
    }

    /**
     * 从分镜提取项目 id：任何异常（含懒加载异常）或为空时返回 null。
     */
    private Long extractProjectId(Shot shot) {
        try {
            return shot.getEpisode().getProject().getId();
        } catch (RuntimeException e) {
            return null;
        }
    }

    /**
     * 在 chain(shot) 给出的候选通道基础上，按评分卡加权分降序重排。
     * 未打分的通道排在最后，并保持其在 chain(shot) 中的原相对顺序；
     * scoreCards 为空时行为与 chain(shot) 完全一致。
     */
    public List<String> rankedChain(Shot shot, Map<String, ProviderScoreCard> scoreCards) {
        List<String> base = chain(shot);
        if (scoreCards == null || scoreCards.isEmpty()) {
            return new ArrayList<>(base);
        }
        List<String> scored = new ArrayList<>();
        List<String> unscored = new ArrayList<>();
        for (String name : base) {
            ProviderScoreCard card = scoreCards.get(name);
            if (card != null) {
                scored.add(name);
            } else {
                unscored.add(name);
            }
        }
        scored.sort(Comparator.comparingDouble(
                (String name) -> scoreCards.get(name).weightedScore()).reversed());
        List<String> result = new ArrayList<>(scored.size() + unscored.size());
        result.addAll(scored);
        result.addAll(unscored);
        return result;
    }

    /**
     * 按评分卡执行路由并记录决策日志。
     * 说明：Shot 类型在本类中仅出现过 submit(Shot,int) 与 chain(Shot) 两种用法，
     * 无法确认其是否存在 getId()，因此 shotId 一律传 null（若后续确认可安全取 ID 再替换）。
     */
    public RoutingDecision routeWithScores(Shot shot, Map<String, ProviderScoreCard> scoreCards, String reason) {
        List<String> ranked = rankedChain(shot, scoreCards);
        String selected = ranked.isEmpty() ? null : ranked.get(0);

        Map<String, Double> scoreMap = new LinkedHashMap<>();
        if (scoreCards != null && !scoreCards.isEmpty()) {
            for (String name : ranked) {
                ProviderScoreCard card = scoreCards.get(name);
                if (card != null) {
                    scoreMap.put(name, card.weightedScore());
                }
            }
        }

        RoutingDecision decision = new RoutingDecision(
                null,
                ranked,
                scoreMap,
                selected,
                reason,
                LocalDateTime.now());

        recordDecision(decision);
        return decision;
    }

    /**
     * 写入决策日志：超过上限丢弃最旧记录；任何异常都不允许向上抛出。
     */
    private void recordDecision(RoutingDecision decision) {
        try {
            synchronized (decisionLog) {
                decisionLog.addLast(decision);
                while (decisionLog.size() > MAX_DECISION_LOG) {
                    decisionLog.pollFirst();
                }
            }
        } catch (RuntimeException e) {
            log.warn("记录路由决策日志失败：{}", e.getMessage());
        }
    }

    /**
     * 返回决策日志快照，顺序为从新到旧。
     */
    public List<RoutingDecision> recentDecisions() {
        try {
            synchronized (decisionLog) {
                List<RoutingDecision> snapshot = new ArrayList<>(decisionLog.size());
                java.util.Iterator<RoutingDecision> it = decisionLog.descendingIterator();
                while (it.hasNext()) {
                    snapshot.add(it.next());
                }
                return snapshot;
            }
        } catch (RuntimeException e) {
            log.warn("读取路由决策日志失败：{}", e.getMessage());
            return new ArrayList<>();
        }
    }

    private String nextName(List<String> chain, int index) {
        if (index + 1 < chain.size()) {
            return chain.get(index + 1);
        }
        return "无可用通道";
    }
}
