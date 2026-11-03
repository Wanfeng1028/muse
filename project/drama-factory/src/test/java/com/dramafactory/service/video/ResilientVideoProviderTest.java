package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link ResilientVideoProvider} 的纯单元测试。
 *
 * <p>不启动 Spring 容器，直接构造注册表与桩实现，聚焦熔断与超时两条路径。</p>
 */
class ResilientVideoProviderTest {

    private CircuitBreakerRegistry circuitBreakerRegistry;
    private TimeLimiterRegistry timeLimiterRegistry;

    @BeforeEach
    void setUp() {
        circuitBreakerRegistry = CircuitBreakerRegistry.of(CircuitBreakerConfig.custom()
                .failureRateThreshold(50)
                .minimumNumberOfCalls(4)
                .slidingWindowSize(10)
                .waitDurationInOpenState(Duration.ofSeconds(60))
                .build());
        timeLimiterRegistry = TimeLimiterRegistry.of(TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofMillis(300))
                .build());
    }

    /**
     * 测试 1：熔断器打开前透出底层 RuntimeException；达到最小调用数后熔断打开，
     * 第 5 次调用抛出 {@link ProviderCircuitOpenException}。
     */
    @Test
    void shouldOpenCircuitAfterFailureThreshold() {
        VideoProvider stub = new VideoProvider() {
            @Override
            public String name() {
                return "stub";
            }

            @Override
            public String submit(Shot shot, int seconds) {
                throw new RuntimeException("boom");
            }

            @Override
            public ProbeResult poll(String providerTaskId) {
                throw new UnsupportedOperationException("not used");
            }
        };
        ResilientVideoProvider provider = new ResilientVideoProvider(stub, circuitBreakerRegistry, timeLimiterRegistry);

        // 连续 4 次：熔断器尚未打开，原异常透出
        for (int i = 0; i < 4; i++) {
            RuntimeException ex = assertThrows(RuntimeException.class,
                    () -> provider.submit(null, 5));
            assertEquals("boom", ex.getMessage());
        }

        // 第 5 次：熔断器已打开（失败率 100% ≥ 50%），被拒绝
        ProviderCircuitOpenException ex = assertThrows(ProviderCircuitOpenException.class,
                () -> provider.submit(null, 5));
        assertTrue(ex.getMessage().contains("熔断器打开"));
    }

    /**
     * 测试 2：TimeLimiter 超时。桩 poll 睡眠 2000ms，超时阈值 300ms，应抛出带 "超时" 的异常。
     */
    @Test
    void shouldTimeoutWhenPollExceedsTimeLimiter() {
        VideoProvider stub = new VideoProvider() {
            @Override
            public String name() {
                return "stub";
            }

            @Override
            public String submit(Shot shot, int seconds) {
                throw new UnsupportedOperationException("not used");
            }

            @Override
            public ProbeResult poll(String providerTaskId) {
                try {
                    Thread.sleep(2000L);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException(e);
                }
                return new ProbeResult(RemoteStatus.COMPLETED, "http://example.com/v.mp4", null, 100);
            }
        };
        ResilientVideoProvider provider = new ResilientVideoProvider(stub, circuitBreakerRegistry, timeLimiterRegistry);

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("task-1"));
        assertTrue(ex.getMessage().contains("超时"), "期望异常消息包含 '超时'，实际为：" + ex.getMessage());
    }
}

