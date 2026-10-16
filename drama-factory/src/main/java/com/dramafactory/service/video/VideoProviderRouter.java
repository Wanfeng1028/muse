package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Component
public class VideoProviderRouter {

    private static final Logger log = LoggerFactory.getLogger(VideoProviderRouter.class);

    private static final List<String> DEFAULT_ORDER = List.of("agnes", "novai", "doubao");
    private static final String MOCK = "mock";

    private final ApplicationContext applicationContext;
    private final Environment environment;
    private final ShotVideoRouter shotVideoRouter;

    private volatile LastFallback lastFallback;

    public VideoProviderRouter(ApplicationContext applicationContext, Environment environment,
                               ShotVideoRouter shotVideoRouter) {
        this.applicationContext = applicationContext;
        this.environment = environment;
        this.shotVideoRouter = shotVideoRouter;
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
        if ("agnes".equals(name)) {
            return applicationContext.getBean("agnesVideoProvider", VideoProvider.class);
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
        if ("painted".equals(name)) {
            return applicationContext.getBean("paintedAnimationVideoProvider", VideoProvider.class);
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

    private String nextName(List<String> chain, int index) {
        if (index + 1 < chain.size()) {
            return chain.get(index + 1);
        }
        return "无可用通道";
    }
}
