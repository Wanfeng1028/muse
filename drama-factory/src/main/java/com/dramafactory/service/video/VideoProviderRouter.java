package com.dramafactory.service.video;

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
     * 最近的路由决策日志，最多保留 50 条，超出时丢弃最旧记录。
     */
    private final Deque<RoutingDecision> decisionLog = new ArrayDeque<>();

    private static final int MAX_DECISION_LOG = 50;

    @org.springframework.beans.factory.annotation.Autowired
    public VideoProviderRouter(ApplicationContext applicationContext, Environment environment,
                               ShotVideoRouter shotVideoRouter, ProviderDescriptorRegistry descriptorRegistry) {
        this.applicationContext = applicationContext;
        this.environment = environment;
        this.shotVideoRouter = shotVideoRouter;
        this.descriptorRegistry = descriptorRegistry;
    }

    /**
     * 测试兼容构造器：descriptorRegistry 为 null 时 descriptor: 通道不可用。
     */
    public VideoProviderRouter(ApplicationContext applicationContext, Environment environment,
                               ShotVideoRouter shotVideoRouter) {
        this(applicationContext, environment, shotVideoRouter, null);
    }


    public record RouteResult(String providerName, String providerTaskId, String fallbackReason) {
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
        List<String> chain = chain(shot);
        List<String> failures = new ArrayList<>();
        for (int i = 0; i < chain.size(); i++) {
            String current = chain.get(i);
            try {
                String providerTaskId = providerFor(current).submit(shot, seconds);
                if (i == 0) {
                    return new RouteResult(current, providerTaskId, null);
                }
                String from = chain.get(0);
                String reason = failures.isEmpty() ? null : failures.get(failures.size() - 1);
                log.warn("视频通道降级：{}→{}，原因={}", from, current, reason);
                lastFallback = new LastFallback(from, current, reason, LocalDateTime.now());
                return new RouteResult(current, providerTaskId, reason);
            } catch (RateLimitedException e) {
                String reason = "限流(429)，" + e.getRetryAfterSeconds() + "秒后可重试";
                failures.add(reason);
                log.warn("视频通道降级：{}→{}，原因={}", current, nextName(chain, i), reason);
            } catch (RuntimeException e) {
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
