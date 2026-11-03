package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.timelimiter.TimeLimiter;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * VideoProviderRouter + ResilientVideoProvider 的失败注入专项深测（第二轮）。
 *
 * <p>覆盖故障场景：下游抛异常自动降级、超时、中断、并发竞态、DB 断开/约束冲突（以 RuntimeException 承载）、
 * 重试耗尽、熔断器打开快速失败、半开恢复、所有 provider 熔断。</p>
 *
 * <p>纯单元测试：provider 一律使用手工 fake stub（实现 VideoProvider 接口），
 * 不 mock 被测核心逻辑本身；仅对 ApplicationContext / Environment 这类外部容器做 mock，
 * 因为它们是需要 Spring 容器才能构造的依赖，测试中无法真实装配。</p>
 */
class VideoProviderRouterFailureDeepTest {

    /** 手工 fake：可编程抛出异常或返回结果，并记录调用次数。 */
    static class FakeVideoProvider implements VideoProvider {
        private final String name;
        private final AtomicInteger submitCalls = new AtomicInteger();
        private volatile RuntimeException submitError;
        private volatile String submitResult = "task-default";
        private volatile ProbeResult pollResult = new ProbeResult(VideoProvider.RemoteStatus.COMPLETED, "http://fake", null, 100);

        FakeVideoProvider(String name) {
            this.name = name;
        }

        FakeVideoProvider failWith(RuntimeException e) {
            this.submitError = e;
            return this;
        }

        FakeVideoProvider succeedWith(String taskId) {
            this.submitError = null;
            this.submitResult = taskId;
            return this;
        }

        FakeVideoProvider pollWith(ProbeResult r) {
            this.pollResult = r;
            return this;
        }

        int submitCalls() {
            return submitCalls.get();
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public String submit(Shot shot, int seconds) {
            submitCalls.incrementAndGet();
            if (submitError != null) {
                throw submitError;
            }
            return submitResult;
        }

        @Override
        public ProbeResult poll(String providerTaskId) {
            return pollResult;
        }
    }

    private Environment envWith(String preferred) {
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn(preferred);
        return env;
    }

    private ApplicationContext ctxWith(String beanName, VideoProvider provider) {
        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq(beanName), eq(VideoProvider.class))).thenReturn(provider);
        return ctx;
    }

    // ---------- 1. 主 provider 抛异常自动降级到备选，状态正确 ----------

    @Test
    void submitPrimaryThrowsFallsBackToSecondaryAndRecordsFallback() {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RuntimeException("主通道故障"));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("task-mm-1");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);
        VideoProviderRouter.RouteResult result = router.submit(null, 5);

        assertThat(result.providerName()).isEqualTo("minimax");
        assertThat(result.providerTaskId()).isEqualTo("task-mm-1");
        assertThat(result.fallbackReason()).isNotNull();
        assertThat(result.fallbackReason()).startsWith("提交异常：");
        assertThat(result.fallbackReason()).contains("主通道故障");

        assertThat(router.lastFallback()).isNotNull();
        assertThat(router.lastFallback().from()).isEqualTo("agnes");
        assertThat(router.lastFallback().to()).isEqualTo("minimax");
        assertThat(router.lastFallback().reason()).contains("主通道故障");
        assertThat(router.lastFallback().at()).isNotNull();

        assertThat(agnes.submitCalls()).isEqualTo(1);
        assertThat(minimax.submitCalls()).isEqualTo(1);
    }

    // ---------- 2. 超时异常被归类为"调用超时" ----------

    @Test
    void submitTimeoutMessageIsClassifiedAsTimeout() {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RuntimeException("调用超时：3000ms 未返回"));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("task-mm-2");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);
        VideoProviderRouter.RouteResult result = router.submit(null, 5);

        assertThat(result.providerName()).isEqualTo("minimax");
        assertThat(result.fallbackReason()).isEqualTo("调用超时");
        assertThat(router.lastFallback()).isNotNull();
        assertThat(router.lastFallback().reason()).isEqualTo("调用超时");
    }

    // ---------- 3. 异常消息超长被截断到 100 字符 ----------

    @Test
    void submitLongExceptionMessageIsTruncatedTo100Chars() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 200; i++) {
            sb.append('x');
        }
        String longMsg = sb.toString();
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RuntimeException(longMsg));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("task-mm-3");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);
        VideoProviderRouter.RouteResult result = router.submit(null, 5);

        assertThat(result.fallbackReason()).isNotNull();
        assertThat(result.fallbackReason()).startsWith("提交异常：");
        // 截断后前缀 + 100 个 x
        String expected = "提交异常：" + longMsg.substring(0, 100);
        assertThat(result.fallbackReason()).isEqualTo(expected);
        assertThat(result.fallbackReason()).hasSize("提交异常：".length() + 100);
    }

    // ---------- 4. 全部 provider 失败时抛出聚合异常，每个都被调用一次 ----------

    @Test
    void submitAllProvidersFailThrowsAggregateWithAllReasons() {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes").failWith(new RuntimeException("a-err"));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").failWith(new RuntimeException("m-err"));
        FakeVideoProvider novai = new FakeVideoProvider("novai").failWith(new RuntimeException("n-err"));
        FakeVideoProvider doubao = new FakeVideoProvider("doubao").failWith(new RuntimeException("d-err"));
        FakeVideoProvider hyper = new FakeVideoProvider("hyperframes").failWith(new RuntimeException("h-err"));
        FakeVideoProvider html = new FakeVideoProvider("htmlrender").failWith(new RuntimeException("r-err"));
        FakeVideoProvider painted = new FakeVideoProvider("painted").failWith(new RuntimeException("p-err"));

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);
        when(ctx.getBean(eq("novAiVideoProvider"), eq(VideoProvider.class))).thenReturn(novai);
        when(ctx.getBean(eq("doubaoEmailVideoProvider"), eq(VideoProvider.class))).thenReturn(doubao);
        when(ctx.getBean(eq("hyperFramesVideoProvider"), eq(VideoProvider.class))).thenReturn(hyper);
        when(ctx.getBean(eq("htmlRenderVideoProvider"), eq(VideoProvider.class))).thenReturn(html);
        when(ctx.getBean(eq("paintedAnimationVideoProvider"), eq(VideoProvider.class))).thenReturn(painted);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);

        assertThatThrownBy(() -> router.submit(null, 5))
                .isInstanceOf(RuntimeException.class)
                .hasMessageStartingWith("所有视频通道均失败：")
                .hasMessageContaining("a-err")
                .hasMessageContaining("m-err")
                .hasMessageContaining("n-err")
                .hasMessageContaining("d-err")
                .hasMessageContaining("h-err")
                .hasMessageContaining("r-err")
                .hasMessageContaining("p-err");

        assertThat(agnes.submitCalls()).isEqualTo(1);
        assertThat(minimax.submitCalls()).isEqualTo(1);
        assertThat(novai.submitCalls()).isEqualTo(1);
        assertThat(doubao.submitCalls()).isEqualTo(1);
        assertThat(hyper.submitCalls()).isEqualTo(1);
        assertThat(html.submitCalls()).isEqualTo(1);
        assertThat(painted.submitCalls()).isEqualTo(1);

        // 全失败时不应写入 lastFallback
        assertThat(router.lastFallback()).isNull();
    }

    // ---------- 5. RateLimitedException 降级后原因保留 retryAfter ----------

    @Test
    void submitRateLimitedPreservesRetryAfterInFallbackReason() {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RateLimitedException("限流", 42));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("task-mm-5");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);
        VideoProviderRouter.RouteResult result = router.submit(null, 5);

        assertThat(result.fallbackReason()).isEqualTo("限流(429)，42秒后可重试");
        assertThat(router.lastFallback()).isNotNull();
        assertThat(router.lastFallback().reason()).isEqualTo("限流(429)，42秒后可重试");
    }

    // ---------- 6. ResilientVideoProvider 熔断打开后快速失败 ----------

    @Test
    void resilientProviderCircuitOpenFailsFastWithoutCallingDelegate() {
        // 用小窗口熔断器：2 次调用 2 次失败即打开。
        CircuitBreakerConfig cbConfig = CircuitBreakerConfig.custom()
                .slidingWindowSize(2)
                .minimumNumberOfCalls(2)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(60))
                .build();
        CircuitBreakerRegistry cbRegistry = CircuitBreakerRegistry.of(cbConfig);
        TimeLimiterRegistry tlRegistry = TimeLimiterRegistry.ofDefaults();

        FakeVideoProvider raw = new FakeVideoProvider("agnes-raw")
                .failWith(new RuntimeException("raw 挂"));

        ResilientVideoProvider provider = new ResilientVideoProvider(raw, cbRegistry, tlRegistry);

        // 触发两次失败让熔断打开
        assertThatThrownBy(() -> provider.submit(null, 5))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("raw 挂");
        assertThatThrownBy(() -> provider.submit(null, 5))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("raw 挂");

        CircuitBreaker cb = cbRegistry.circuitBreaker("agnes");
        assertThat(cb.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        int callsBefore = raw.submitCalls();
        // 熔断打开后应直接抛 ProviderCircuitOpenException，不再调用 delegate
        assertThatThrownBy(() -> provider.submit(null, 5))
                .isInstanceOf(ProviderCircuitOpenException.class)
                .hasMessageContaining("agnes 熔断器打开");
        assertThat(raw.submitCalls()).isEqualTo(callsBefore);
    }

    // ---------- 7. ResilientVideoProvider 熔断半开恢复 ----------

    @Test
    void resilientProviderHalfOpenRecoversAfterWaitDuration() throws Exception {
        CircuitBreakerConfig cbConfig = CircuitBreakerConfig.custom()
                .slidingWindowSize(2)
                .minimumNumberOfCalls(2)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofMillis(300))
                .permittedNumberOfCallsInHalfOpenState(1)
                .build();
        CircuitBreakerRegistry cbRegistry = CircuitBreakerRegistry.of(cbConfig);
        TimeLimiterRegistry tlRegistry = TimeLimiterRegistry.ofDefaults();

        FakeVideoProvider raw = new FakeVideoProvider("agnes-raw")
                .failWith(new RuntimeException("raw 挂"));
        ResilientVideoProvider provider = new ResilientVideoProvider(raw, cbRegistry, tlRegistry);

        assertThatThrownBy(() -> provider.submit(null, 5)).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(() -> provider.submit(null, 5)).isInstanceOf(RuntimeException.class);
        CircuitBreaker cb = cbRegistry.circuitBreaker("agnes");
        assertThat(cb.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // Resilience4j 熔断器是惰性转移：waitDuration 过后状态仍为 OPEN，
        // 下一次调用时才进入 HALF_OPEN 并放行试探调用
        Thread.sleep(400);
        assertThat(cb.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // 放行成功调用：触发 HALF_OPEN 试探，成功后回到 CLOSED
        raw.succeedWith("recovered-task");
        String taskId = provider.submit(null, 5);
        assertThat(taskId).isEqualTo("recovered-task");
        assertThat(cb.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
    }

    // ---------- 8. ResilientVideoProvider 超时被转为 RuntimeException ----------

    @Test
    void resilientProviderTimeLimiterTimeoutIsTranslated() {
        CircuitBreakerConfig cbConfig = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(90.0f)
                .build();
        CircuitBreakerRegistry cbRegistry = CircuitBreakerRegistry.of(cbConfig);
        TimeLimiterConfig tlConfig = TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofMillis(50))
                .cancelRunningFuture(true)
                .build();
        TimeLimiterRegistry tlRegistry = TimeLimiterRegistry.of(tlConfig);

        VideoProvider slow = new VideoProvider() {
            @Override
            public String name() {
                return "agnes-raw";
            }

            @Override
            public String submit(Shot shot, int seconds) {
                try {
                    Thread.sleep(2000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                return "late";
            }

            @Override
            public ProbeResult poll(String providerTaskId) {
                return new ProbeResult(VideoProvider.RemoteStatus.PROCESSING, null, null, 0);
            }
        };

        ResilientVideoProvider provider = new ResilientVideoProvider(slow, cbRegistry, tlRegistry);

        assertThatThrownBy(() -> provider.submit(null, 5))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("agnes 调用超时");
    }

    // ---------- 9. 并发 submit 降级一致性 ----------

    @Test
    void concurrentSubmitFallbackIsConsistent() throws Exception {
        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            List<Future<VideoProviderRouter.RouteResult>> futures = new ArrayList<>();
            CountDownLatch start = new CountDownLatch(1);

            for (int i = 0; i < threads; i++) {
                futures.add(pool.submit(() -> {
                    // 每个线程独立构造 router，共享同一个已失败的 agnes stub
                    FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                            .failWith(new RuntimeException("主通道故障"));
                    FakeVideoProvider minimax = new FakeVideoProvider("minimax")
                            .succeedWith("task-concurrent");

                    ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
                    when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
                    when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

                    VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);
                    start.await();
                    return router.submit(null, 5);
                }));
            }

            start.countDown();
            for (Future<VideoProviderRouter.RouteResult> f : futures) {
                VideoProviderRouter.RouteResult r = f.get(10, TimeUnit.SECONDS);
                assertThat(r.providerName()).isEqualTo("minimax");
                assertThat(r.providerTaskId()).isEqualTo("task-concurrent");
                assertThat(r.fallbackReason()).contains("主通道故障");
            }
        } finally {
            pool.shutdownNow();
        }
    }

    // ---------- 10. 并发提交单个 router 时 lastFallback 状态不被破坏 ----------

    @Test
    void concurrentSubmitOnSharedRouterKeepsLastFallbackConsistent() throws Exception {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RuntimeException("共享主通道故障"));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("shared-task");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);

        int threads = 16;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            CountDownLatch start = new CountDownLatch(1);
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 0; i < threads; i++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    return router.submit(null, 5).providerName();
                }));
            }
            start.countDown();
            for (Future<String> f : futures) {
                assertThat(f.get(10, TimeUnit.SECONDS)).isEqualTo("minimax");
            }
        } finally {
            pool.shutdownNow();
        }

        // lastFallback 由成功降级路径写入，字段最终应稳定指向 agnes→minimax
        VideoProviderRouter.LastFallback lf = router.lastFallback();
        assertThat(lf).isNotNull();
        assertThat(lf.from()).isEqualTo("agnes");
        assertThat(lf.to()).isEqualTo("minimax");
        assertThat(lf.reason()).contains("共享主通道故障");
        // agnes 被调用次数 == 线程数
        assertThat(agnes.submitCalls()).isEqualTo(threads);
        assertThat(minimax.submitCalls()).isEqualTo(threads);
    }

    // ---------- 11. 下游中断（InterruptedException 包装成 RuntimeException）也能降级 ----------

    @Test
    void submitInterruptedWrappedRuntimeExceptionStillFallsBack() {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RuntimeException("提交被中断：InterruptedException"));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("task-after-interrupt");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);
        VideoProviderRouter.RouteResult result = router.submit(null, 5);

        assertThat(result.providerName()).isEqualTo("minimax");
        assertThat(result.providerTaskId()).isEqualTo("task-after-interrupt");
        assertThat(result.fallbackReason()).contains("提交被中断");
    }

    // ---------- 12. 数据库断开/约束冲突以 RuntimeException 承载，仍能降级 ----------

    @Test
    void submitDbDisconnectRuntimeExceptionTriggersFallback() {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RuntimeException("JDBCConnectionException: 连接已断开"));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("task-db-ok");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);
        VideoProviderRouter.RouteResult result = router.submit(null, 5);

        assertThat(result.providerName()).isEqualTo("minimax");
        assertThat(result.fallbackReason()).contains("JDBCConnectionException");
        assertThat(router.lastFallback()).isNotNull();
        assertThat(router.lastFallback().from()).isEqualTo("agnes");
    }

    @Test
    void submitConstraintViolationRuntimeExceptionTriggersFallback() {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RuntimeException("ConstraintViolationException: uk_task_id 冲突"));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("task-uk-ok");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);
        VideoProviderRouter.RouteResult result = router.submit(null, 5);

        assertThat(result.providerName()).isEqualTo("minimax");
        assertThat(result.fallbackReason()).contains("ConstraintViolationException");
    }

    // ---------- 13. 重试耗尽：连续多个 provider 均 429 后全部失败 ----------

    @Test
    void submitRetryExhaustedAcrossMultipleRateLimitedProvidersThrowsAggregate() {
        FakeVideoProvider agnes = new FakeVideoProvider("agnes")
                .failWith(new RateLimitedException("限流", 10));
        FakeVideoProvider minimax = new FakeVideoProvider("minimax")
                .failWith(new RateLimitedException("限流", 20));
        FakeVideoProvider novai = new FakeVideoProvider("novai")
                .failWith(new RateLimitedException("限流", 30));

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(agnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);
        when(ctx.getBean(eq("novAiVideoProvider"), eq(VideoProvider.class))).thenReturn(novai);
        // 后面几个也返回限流，确保重试全部耗尽
        FakeVideoProvider doubao = new FakeVideoProvider("doubao")
                .failWith(new RateLimitedException("限流", 40));
        FakeVideoProvider hyper = new FakeVideoProvider("hyperframes")
                .failWith(new RateLimitedException("限流", 50));
        FakeVideoProvider html = new FakeVideoProvider("htmlrender")
                .failWith(new RateLimitedException("限流", 60));
        FakeVideoProvider painted = new FakeVideoProvider("painted")
                .failWith(new RateLimitedException("限流", 70));
        when(ctx.getBean(eq("doubaoEmailVideoProvider"), eq(VideoProvider.class))).thenReturn(doubao);
        when(ctx.getBean(eq("hyperFramesVideoProvider"), eq(VideoProvider.class))).thenReturn(hyper);
        when(ctx.getBean(eq("htmlRenderVideoProvider"), eq(VideoProvider.class))).thenReturn(html);
        when(ctx.getBean(eq("paintedAnimationVideoProvider"), eq(VideoProvider.class))).thenReturn(painted);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);

        assertThatThrownBy(() -> router.submit(null, 5))
                .isInstanceOf(RuntimeException.class)
                .hasMessageStartingWith("所有视频通道均失败：")
                .hasMessageContaining("限流(429)，10秒后可重试")
                .hasMessageContaining("限流(429)，20秒后可重试")
                .hasMessageContaining("限流(429)，30秒后可重试")
                .hasMessageContaining("限流(429)，40秒后可重试")
                .hasMessageContaining("限流(429)，50秒后可重试")
                .hasMessageContaining("限流(429)，60秒后可重试")
                .hasMessageContaining("限流(429)，70秒后可重试");

        assertThat(agnes.submitCalls()).isEqualTo(1);
        assertThat(minimax.submitCalls()).isEqualTo(1);
        assertThat(novai.submitCalls()).isEqualTo(1);
        assertThat(doubao.submitCalls()).isEqualTo(1);
        assertThat(hyper.submitCalls()).isEqualTo(1);
        assertThat(html.submitCalls()).isEqualTo(1);
        assertThat(painted.submitCalls()).isEqualTo(1);
        assertThat(router.lastFallback()).isNull();
    }

    // ---------- 14. ResilientVideoProvider poll 熔断打开也抛 ProviderCircuitOpenException ----------

    @Test
    void resilientProviderPollFailsFastWhenCircuitOpen() {
        CircuitBreakerConfig cbConfig = CircuitBreakerConfig.custom()
                .slidingWindowSize(2)
                .minimumNumberOfCalls(2)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(60))
                .build();
        CircuitBreakerRegistry cbRegistry = CircuitBreakerRegistry.of(cbConfig);
        TimeLimiterRegistry tlRegistry = TimeLimiterRegistry.ofDefaults();

        VideoProvider raw = new VideoProvider() {
            @Override
            public String name() {
                return "agnes-raw";
            }

            @Override
            public String submit(Shot shot, int seconds) {
                throw new RuntimeException("submit 挂");
            }

            @Override
            public ProbeResult poll(String providerTaskId) {
                throw new RuntimeException("poll 挂");
            }
        };

        ResilientVideoProvider provider = new ResilientVideoProvider(raw, cbRegistry, tlRegistry);

        assertThatThrownBy(() -> provider.poll("t1")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(() -> provider.poll("t1")).isInstanceOf(RuntimeException.class);

        CircuitBreaker cb = cbRegistry.circuitBreaker("agnes");
        assertThat(cb.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        assertThatThrownBy(() -> provider.poll("t1"))
                .isInstanceOf(ProviderCircuitOpenException.class)
                .hasMessageContaining("agnes 熔断器打开");
    }

    // ---------- 15. ResilientVideoProvider 底层 RateLimitedException 原样透出 ----------

    @Test
    void resilientProviderPreservesRateLimitedExceptionType() {
        CircuitBreakerRegistry cbRegistry = CircuitBreakerRegistry.ofDefaults();
        TimeLimiterRegistry tlRegistry = TimeLimiterRegistry.ofDefaults();

        FakeVideoProvider raw = new FakeVideoProvider("agnes-raw")
                .failWith(new RateLimitedException("限流", 15));

        ResilientVideoProvider provider = new ResilientVideoProvider(raw, cbRegistry, tlRegistry);

        assertThatThrownBy(() -> provider.submit(null, 5))
                .isInstanceOf(RateLimitedException.class)
                .hasMessage("限流");
    }

    // ---------- 16. 熔断器打开后 router 仍能降级到备选（真实链路验证） ----------

    @Test
    void routerFallsBackWhenResilientAgnesCircuitOpen() {
        // agnes 是 ResilientVideoProvider，熔断打开后抛 ProviderCircuitOpenException；
        // router 应把它当作 RuntimeException 捕获并降级到 minimax。
        CircuitBreakerConfig cbConfig = CircuitBreakerConfig.custom()
                .slidingWindowSize(2)
                .minimumNumberOfCalls(2)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(60))
                .build();
        CircuitBreakerRegistry cbRegistry = CircuitBreakerRegistry.of(cbConfig);
        TimeLimiterRegistry tlRegistry = TimeLimiterRegistry.ofDefaults();

        FakeVideoProvider rawAgnes = new FakeVideoProvider("agnes-raw")
                .failWith(new RuntimeException("raw agnes 挂"));
        ResilientVideoProvider resilientAgnes = new ResilientVideoProvider(rawAgnes, cbRegistry, tlRegistry);

        FakeVideoProvider minimax = new FakeVideoProvider("minimax").succeedWith("task-fallback-cb");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        when(ctx.getBean(eq("agnesVideoProvider"), eq(VideoProvider.class))).thenReturn(resilientAgnes);
        when(ctx.getBean(eq("miniMaxH3VideoProvider"), eq(VideoProvider.class))).thenReturn(minimax);

        VideoProviderRouter router = new VideoProviderRouter(ctx, envWith("agnes"), null);

        // 前两次调用触发熔断打开，均降级到 minimax
        VideoProviderRouter.RouteResult r1 = router.submit(null, 5);
        assertThat(r1.providerName()).isEqualTo("minimax");
        VideoProviderRouter.RouteResult r2 = router.submit(null, 5);
        assertThat(r2.providerName()).isEqualTo("minimax");

        CircuitBreaker cb = cbRegistry.circuitBreaker("agnes");
        assertThat(cb.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // 第三次：熔断打开，agnes 直接拒绝，router 仍降级
        VideoProviderRouter.RouteResult r3 = router.submit(null, 5);
        assertThat(r3.providerName()).isEqualTo("minimax");
        assertThat(r3.fallbackReason()).isNotNull();
        assertThat(r3.fallbackReason()).contains("agnes 熔断器打开");

        // 底层 raw agnes 只在熔断打开前被调用过 2 次
        assertThat(rawAgnes.submitCalls()).isEqualTo(2);
        assertThat(minimax.submitCalls()).isEqualTo(3);
    }

    // ---------- 17. ResilientVideoProvider name() 返回 agnes ----------

    @Test
    void resilientProviderNameIsAgnes() {
        CircuitBreakerRegistry cbRegistry = CircuitBreakerRegistry.ofDefaults();
        TimeLimiterRegistry tlRegistry = TimeLimiterRegistry.ofDefaults();
        FakeVideoProvider raw = new FakeVideoProvider("agnes-raw");
        ResilientVideoProvider provider = new ResilientVideoProvider(raw, cbRegistry, tlRegistry);
        assertThat(provider.name()).isEqualTo("agnes");
    }
}
