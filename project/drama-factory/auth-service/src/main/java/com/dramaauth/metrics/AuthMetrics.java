package com.dramaauth.metrics;

import com.dramaauth.repository.SessionRepository;
import com.dramaauth.repository.UserRepository;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.concurrent.atomic.AtomicLong;

/**
 * auth-service 指标采集组件，对标主服务 v2.4 的 DramaMetrics 模式。
 *
 * <p>设计原则：
 * <ul>
 *   <li><b>Counter 业务点同步记</b>：注册、登录、刷新、OAuth 回调在业务方法内直接 +1，
 *       与业务事务解耦（指标不做回滚），标签基数可控（result 仅 success|failure，
 *       provider 为小写渠道名）。</li>
 *   <li><b>Gauge 快照</b>：用户总数、活跃会话数由 {@link #refresh()} 周期性写入
 *       AtomicLong，Prometheus 抓取时只读内存值，不在 scrape 路径上查库，
 *       避免抓取抖动传导到数据库。</li>
 *   <li><b>刷新异常隔离</b>：{@link #refresh()} 内部吞掉 DB 异常并打 warn，
 *       保证指标刷新失败不会中断定时任务线程、更不会影响业务请求。</li>
 * </ul>
 *
 * <p>指标一览：
 * <ul>
 *   <li>{@code dramaauth_registrations_total} —— 累计注册用户数（个）</li>
 *   <li>{@code dramaauth_logins_total{result}} —— 登录尝试按结果计数（success|failure）</li>
 *   <li>{@code dramaauth_token_refreshes_total{result}} —— refresh token 轮换按结果计数（success|failure）</li>
 *   <li>{@code dramaauth_oauth_callbacks_total{provider,result}} —— OAuth 回调按渠道与结果计数</li>
 *   <li>{@code dramaauth_users_total} —— 当前用户总数（瞬时值）</li>
 *   <li>{@code dramaauth_sessions_active} —— 当前未撤销且未过期的活跃会话数（瞬时值）</li>
 * </ul>
 */
@Component
public class AuthMetrics {

    private static final Logger log = LoggerFactory.getLogger(AuthMetrics.class);

    private final Counter registrationsTotal;
    private final Counter loginsSuccess;
    private final Counter loginsFailure;
    private final Counter refreshesSuccess;
    private final Counter refreshesFailure;

    private final UserRepository userRepository;
    private final SessionRepository sessionRepository;

    private final MeterRegistry registryRef;
    private final java.util.concurrent.ConcurrentHashMap<String, Counter> oauthCallbacks =
            new java.util.concurrent.ConcurrentHashMap<>();

    private final AtomicLong usersTotal = new AtomicLong(0L);
    private final AtomicLong sessionsActive = new AtomicLong(0L);

    public AuthMetrics(MeterRegistry registry, UserRepository userRepository, SessionRepository sessionRepository) {
        this.registryRef = registry;
        this.userRepository = userRepository;
        this.sessionRepository = sessionRepository;

        this.registrationsTotal = Counter.builder("dramaauth_registrations_total")
                .description("累计注册用户数，单位：个")
                .register(registry);

        this.loginsSuccess = Counter.builder("dramaauth_logins_total")
                .description("登录尝试按结果计数")
                .tag("result", "success")
                .register(registry);

        this.loginsFailure = Counter.builder("dramaauth_logins_total")
                .description("登录尝试按结果计数")
                .tag("result", "failure")
                .register(registry);

        this.refreshesSuccess = Counter.builder("dramaauth_token_refreshes_total")
                .description("refresh token 轮换按结果计数")
                .tag("result", "success")
                .register(registry);

        this.refreshesFailure = Counter.builder("dramaauth_token_refreshes_total")
                .description("refresh token 轮换按结果计数")
                .tag("result", "failure")
                .register(registry);

        Gauge.builder("dramaauth_users_total", usersTotal, AtomicLong::get)
                .description("当前用户总数，单位：个")
                .register(registry);

        Gauge.builder("dramaauth_sessions_active", sessionsActive, AtomicLong::get)
                .description("当前未撤销且未过期的活跃会话数，单位：个")
                .register(registry);
    }

    /** 记录一次成功注册。 */
    public void recordRegistration() {
        registrationsTotal.increment();
    }

    /** 记录一次登录尝试。 */
    public void recordLogin(boolean success) {
        if (success) {
            loginsSuccess.increment();
        } else {
            loginsFailure.increment();
        }
    }

    /** 记录一次 refresh token 轮换。 */
    public void recordRefresh(boolean success) {
        if (success) {
            refreshesSuccess.increment();
        } else {
            refreshesFailure.increment();
        }
    }

    /** 记录一次 OAuth 回调；provider 需为小写渠道名。 */
    public void recordOAuthCallback(String provider, boolean success) {
        String p = provider == null ? "unknown" : provider.toLowerCase();
        oauthCallbacks.computeIfAbsent(p + "|" + (success ? "success" : "failure"),
                k -> Counter.builder("dramaauth_oauth_callbacks_total")
                        .description("OAuth 回调按渠道与结果计数")
                        .tag("provider", p)
                        .tag("result", success ? "success" : "failure")
                        .register(registryRef))
                .increment();
    }

    /** 周期性刷新 Gauge 快照；DB 异常只打 warn，不中断。 */
    @Scheduled(fixedDelay = 30000)
    public void refresh() {
        try {
            usersTotal.set(userRepository.count());
            sessionsActive.set(sessionRepository.countByRevokedFalseAndExpiresAtAfter(LocalDateTime.now()));
        } catch (Exception e) {
            log.warn("刷新 auth 指标快照失败，保留上一次值", e);
        }
    }
}
