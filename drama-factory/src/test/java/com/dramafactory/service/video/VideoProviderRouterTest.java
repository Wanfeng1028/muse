package com.dramafactory.service.video;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import com.dramafactory.model.Shot;

class VideoProviderRouterTest {

    private static final String AGNES = "agnes";
    private static final String QWEN = "qwen";
    private static final String MOCK = "mock";

    private static VideoProvider stubProvider(String name, SubmitBehavior behavior) {
        return new VideoProvider() {
            @Override
            public String name() {
                return name;
            }

            @Override
            public String submit(Shot shot, int seconds) {
                return behavior.submit(name);
            }

            @Override
            public VideoProvider.ProbeResult poll(String taskId) {
                throw new UnsupportedOperationException();
            }
        };
    }

    @FunctionalInterface
    private interface SubmitBehavior {
        String submit(String name);
    }

    private static VideoProvider successProvider(String name) {
        return stubProvider(name, n -> n + "-task");
    }

    private static VideoProvider failingProvider(String name, RuntimeException toThrow) {
        return stubProvider(name, n -> {
            throw toThrow;
        });
    }

    private static Environment environmentWithPreferred(String preferred) {
        Environment env = mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn(preferred);
        return env;
    }

    private static ApplicationContext contextWith(VideoProvider agnes, VideoProvider qwen, VideoProvider mock) {
        ApplicationContext ctx = mock(ApplicationContext.class);
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(ctx.getBean("qwenVideoProvider", VideoProvider.class)).thenReturn(qwen);
        when(ctx.getBean("mockVideoProvider", VideoProvider.class)).thenReturn(mock);
        return ctx;
    }

    private static Shot shot() {
        return new Shot();
    }

    @Test
    void preferredAgnesSucceedsWithoutFallback() {
        VideoProvider agnes = successProvider(AGNES);
        VideoProvider qwen = successProvider(QWEN);
        VideoProvider mock = successProvider(MOCK);
        ApplicationContext ctx = contextWith(agnes, qwen, mock);
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        VideoProviderRouter.RouteResult result = router.submit(shot(), 5);

        assertEquals(AGNES, result.providerName());
        assertEquals("agnes-task", result.providerTaskId());
        assertNull(result.fallbackReason());
        assertNull(router.lastFallback());
    }

    @Test
    void chainPrefersQwenThenAgnes() {
        ApplicationContext ctx = contextWith(successProvider(AGNES), successProvider(QWEN), successProvider(MOCK));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(QWEN), null);

        assertEquals(List.of(QWEN, AGNES), router.chain());
    }

    @Test
    void chainPrefersMockOnly() {
        ApplicationContext ctx = contextWith(successProvider(AGNES), successProvider(QWEN), successProvider(MOCK));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(MOCK), null);

        assertEquals(List.of(MOCK), router.chain());
    }

    @Test
    void mockFailureDoesNotFallBackToAgnesOrQwen() {
        RuntimeException boom = new RuntimeException("mock down");
        ApplicationContext ctx = contextWith(successProvider(AGNES), successProvider(QWEN), failingProvider(MOCK, boom));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(MOCK), null);

        RuntimeException thrown = assertThrows(RuntimeException.class, () -> router.submit(shot(), 5));
        assertTrue(thrown.getMessage().contains("所有视频通道均失败"));
    }

    @Test
    void agnesRateLimitedFallsBackToQwen() {
        VideoProvider agnes = failingProvider(AGNES, new RateLimitedException("agnes 限流", 60));
        VideoProvider qwen = successProvider(QWEN);
        VideoProvider mock = successProvider(MOCK);
        ApplicationContext ctx = contextWith(agnes, qwen, mock);
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        VideoProviderRouter.RouteResult result = router.submit(shot(), 5);

        assertEquals(QWEN, result.providerName());
        assertEquals("qwen-task", result.providerTaskId());
        assertNotNull(result.fallbackReason());
        assertTrue(result.fallbackReason().contains("限流(429)"));
        assertTrue(result.fallbackReason().contains("60"));

        VideoProviderRouter.LastFallback last = router.lastFallback();
        assertNotNull(last);
        assertEquals(AGNES, last.from());
        assertEquals(QWEN, last.to());
    }

    @Test
    void agnesTimeoutFallsBackToQwen() {
        VideoProvider agnes = failingProvider(AGNES, new RuntimeException("agnes 调用超时（TimeLimiter）"));
        VideoProvider qwen = successProvider(QWEN);
        VideoProvider mock = successProvider(MOCK);
        ApplicationContext ctx = contextWith(agnes, qwen, mock);
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        VideoProviderRouter.RouteResult result = router.submit(shot(), 5);

        assertEquals(QWEN, result.providerName());
        assertEquals("调用超时", result.fallbackReason());

        VideoProviderRouter.LastFallback last = router.lastFallback();
        assertNotNull(last);
        assertEquals(AGNES, last.from());
        assertEquals(QWEN, last.to());
    }

    @Test
    void agnesGenericExceptionFallsBackToQwen() {
        VideoProvider agnes = failingProvider(AGNES, new RuntimeException("boom"));
        VideoProvider qwen = successProvider(QWEN);
        VideoProvider mock = successProvider(MOCK);
        ApplicationContext ctx = contextWith(agnes, qwen, mock);
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        VideoProviderRouter.RouteResult result = router.submit(shot(), 5);

        assertEquals(QWEN, result.providerName());
        assertNotNull(result.fallbackReason());
        assertTrue(result.fallbackReason().contains("提交异常"));
        assertTrue(result.fallbackReason().contains("boom"));

        VideoProviderRouter.LastFallback last = router.lastFallback();
        assertNotNull(last);
        assertEquals(AGNES, last.from());
        assertEquals(QWEN, last.to());
    }

    @Test
    void allProvidersFailThrowsRuntimeException() {
        VideoProvider agnes = failingProvider(AGNES, new RuntimeException("agnes down"));
        VideoProvider qwen = failingProvider(QWEN, new RuntimeException("qwen down"));
        VideoProvider mock = successProvider(MOCK);
        ApplicationContext ctx = contextWith(agnes, qwen, mock);
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        RuntimeException thrown = assertThrows(RuntimeException.class, () -> router.submit(shot(), 5));
        assertTrue(thrown.getMessage().contains("所有视频通道均失败"));
    }

    @Test
    void providerForUnknownNameThrowsIllegalArgumentException() {
        ApplicationContext ctx = contextWith(successProvider(AGNES), successProvider(QWEN), successProvider(MOCK));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        assertThrows(IllegalArgumentException.class, () -> router.providerFor("unknown"));
    }
}
