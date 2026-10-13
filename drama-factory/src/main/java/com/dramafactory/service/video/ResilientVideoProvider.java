package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.timelimiter.TimeLimiter;
import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeoutException;

/**
 * {@link VideoProvider} 的弹性装饰器。
 *
 * <p>在不改动底层真实实现（{@code agnesRawVideoProvider}）与业务编排（{@code VideoTaskService}）
 * 的前提下，通过 Spring Bean 名称覆盖的方式（注册为 {@code "agnesVideoProvider"}）无缝接入
 * Resilience4j 的熔断（CircuitBreaker）与超时（TimeLimiter）能力。</p>
 *
 * <p>关键行为：</p>
 * <ul>
 *     <li>熔断器实例名：{@code "agnes"}；超时器实例名：{@code "agnes"}。</li>
 *     <li>熔断打开时抛出 {@link ProviderCircuitOpenException}，由上层 failOrRetry 统一重试。</li>
 *     <li>底层抛出的 RuntimeException（如限流异常 {@code RateLimitedException}）原样透出，
 *         不做二次包装，便于上层做精确的类型判断与重试策略。</li>
 * </ul>
 */
@Component("agnesVideoProvider")
public class ResilientVideoProvider implements VideoProvider {

    private final VideoProvider delegate;
    private final CircuitBreakerRegistry circuitBreakerRegistry;
    private final TimeLimiterRegistry timeLimiterRegistry;

    /**
     * 构造器注入。
     *
     * @param delegate               真实实现（bean 名 agnesRawVideoProvider）
     * @param circuitBreakerRegistry 熔断器注册表
     * @param timeLimiterRegistry    超时器注册表
     */
    public ResilientVideoProvider(@Qualifier("agnesRawVideoProvider") VideoProvider delegate,
                                  CircuitBreakerRegistry circuitBreakerRegistry,
                                  TimeLimiterRegistry timeLimiterRegistry) {
        this.delegate = delegate;
        this.circuitBreakerRegistry = circuitBreakerRegistry;
        this.timeLimiterRegistry = timeLimiterRegistry;
    }

    @Override
    public String name() {
        return "agnes";
    }

    @Override
    public String submit(Shot shot, int seconds) {
        return execute(() -> delegate.submit(shot, seconds));
    }

    @Override
    public ProbeResult poll(String providerTaskId) {
        return execute(() -> delegate.poll(providerTaskId));
    }

    /**
     * 统一包装：同时应用熔断 + 超时。
     *
     * <p>注意 {@link TimeLimiter#decorateFutureSupplier} 需要运行在独立线程中，否则主线程阻塞
     * 无法被中断；这里使用 {@link CompletableFuture#supplyAsync} 将真实调用放到 ForkJoinPool
     * 公共池执行，从而让 TimeLimiter 能在超时时取消等待。</p>
     *
     * @param callable 待执行的业务调用
     * @param <T>      返回类型
     * @return 业务调用结果
     */
    private <T> T execute(Callable<T> callable) {
        CircuitBreaker cb = circuitBreakerRegistry.circuitBreaker("agnes");
        TimeLimiter tl = timeLimiterRegistry.timeLimiter("agnes");
        Callable<T> decorated = CircuitBreaker.decorateCallable(cb,
                TimeLimiter.decorateFutureSupplier(tl, () -> CompletableFuture.supplyAsync(() -> {
                    try {
                        return callable.call();
                    } catch (Exception e) {
                        throw new CompletionException(e);
                    }
                })));
        try {
            return decorated.call();
        } catch (CallNotPermittedException e) {
            throw new ProviderCircuitOpenException("agnes 熔断器打开，请求被拒绝", e);
        } catch (TimeoutException e) {
            throw new RuntimeException("agnes 调用超时（TimeLimiter）", e);
        } catch (RuntimeException e) {
            // TimeLimiter / CircuitBreaker 会把 delegate 抛出的原始 RuntimeException
            //（如 RateLimitedException）原样透出，这里直接透传，不做二次包装
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("agnes 调用失败", e);
        }
    }
}

