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
    private static final String MINIMAX = "minimax";
    private static final String NOVAI = "novai";
    private static final String DOUBAO = "doubao";
    private static final String PAINTED = "painted";
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

    private static ApplicationContext contextWithAll() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(successProvider(AGNES));
        when(ctx.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(successProvider(NOVAI));
        when(ctx.getBean("doubaoEmailVideoProvider", VideoProvider.class)).thenReturn(successProvider(DOUBAO));
        when(ctx.getBean("paintedAnimationVideoProvider", VideoProvider.class)).thenReturn(successProvider(PAINTED));
        when(ctx.getBean("mockVideoProvider", VideoProvider.class)).thenReturn(successProvider(MOCK));
        return ctx;
    }

    private static Shot shot() {
        return new Shot();
    }

    @Test
    void preferredAgnesSucceedsWithoutFallback() {
        VideoProviderRouter router = new VideoProviderRouter(contextWithAll(), environmentWithPreferred(AGNES), null);

        VideoProviderRouter.RouteResult result = router.submit(shot(), 5);

        assertEquals(AGNES, result.providerName());
        assertEquals("agnes-task", result.providerTaskId());
        assertNull(result.fallbackReason());
        assertNull(router.lastFallback());
    }

    @Test
    void chainOrderAgnesFirstThenDefaultFallbacks() {
        VideoProviderRouter router = new VideoProviderRouter(contextWithAll(), environmentWithPreferred(AGNES), null);

        // 2026-10-16 起 qwen 因额度耗尽摘除；本地兜底通道 htmlrender/painted 仍在
        // DEFAULT_ORDER，链：agnes → minimax → novai → doubao → htmlrender → painted
        assertEquals(List.of(AGNES, MINIMAX, NOVAI, DOUBAO, "htmlrender", PAINTED), router.chain());
    }

    @Test
    void chainPrefersMockOnly() {
        VideoProviderRouter router = new VideoProviderRouter(contextWithAll(), environmentWithPreferred(MOCK), null);

        assertEquals(List.of(MOCK), router.chain());
    }

    @Test
    void mockFailureDoesNotFallBack() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        when(ctx.getBean("mockVideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(MOCK, new RuntimeException("mock down")));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(MOCK), null);

        RuntimeException thrown = assertThrows(RuntimeException.class, () -> router.submit(shot(), 5));
        assertTrue(thrown.getMessage().contains("所有视频通道均失败"));
    }

    @Test
    void agnesRateLimitedFallsBackToNovai() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(AGNES, new RateLimitedException("agnes 限流", 60)));
        when(ctx.getBean("miniMaxH3VideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(MINIMAX, new RateLimitedException("minimax 限流", 60)));
        when(ctx.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(successProvider(NOVAI));
        when(ctx.getBean("doubaoEmailVideoProvider", VideoProvider.class)).thenReturn(successProvider(DOUBAO));
        when(ctx.getBean("mockVideoProvider", VideoProvider.class)).thenReturn(successProvider(MOCK));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        VideoProviderRouter.RouteResult result = router.submit(shot(), 5);

        assertEquals(NOVAI, result.providerName());
        assertEquals("novai-task", result.providerTaskId());
        assertNotNull(result.fallbackReason());
        assertTrue(result.fallbackReason().contains("限流(429)"));

        VideoProviderRouter.LastFallback last = router.lastFallback();
        assertNotNull(last);
        assertEquals(AGNES, last.from());
        assertEquals(NOVAI, last.to());
    }

    @Test
    void agnesTimeoutFallsBackToNovai() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(AGNES, new RuntimeException("agnes 调用超时（TimeLimiter）")));
        when(ctx.getBean("miniMaxH3VideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(MINIMAX, new RuntimeException("minimax 调用超时")));
        when(ctx.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(successProvider(NOVAI));
        when(ctx.getBean("doubaoEmailVideoProvider", VideoProvider.class)).thenReturn(successProvider(DOUBAO));
        when(ctx.getBean("mockVideoProvider", VideoProvider.class)).thenReturn(successProvider(MOCK));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        VideoProviderRouter.RouteResult result = router.submit(shot(), 5);

        assertEquals(NOVAI, result.providerName());
        assertEquals("调用超时", result.fallbackReason());
    }

    @Test
    void agnesGenericExceptionFallsBackToNovai() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(AGNES, new RuntimeException("boom")));
        when(ctx.getBean("miniMaxH3VideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(MINIMAX, new RuntimeException("boom2")));
        when(ctx.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(successProvider(NOVAI));
        when(ctx.getBean("doubaoEmailVideoProvider", VideoProvider.class)).thenReturn(successProvider(DOUBAO));
        when(ctx.getBean("mockVideoProvider", VideoProvider.class)).thenReturn(successProvider(MOCK));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        VideoProviderRouter.RouteResult result = router.submit(shot(), 5);

        assertEquals(NOVAI, result.providerName());
        assertNotNull(result.fallbackReason());
        assertTrue(result.fallbackReason().contains("提交异常"));
        assertTrue(result.fallbackReason().contains("boom"));
    }

    @Test
    void allProvidersFailThrowsRuntimeException() {
        ApplicationContext ctx = mock(ApplicationContext.class);
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(AGNES, new RuntimeException("agnes down")));
        when(ctx.getBean("novAiVideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(NOVAI, new RuntimeException("novai down")));
        when(ctx.getBean("doubaoEmailVideoProvider", VideoProvider.class))
                .thenReturn(failingProvider(DOUBAO, new RuntimeException("doubao down")));
        when(ctx.getBean("mockVideoProvider", VideoProvider.class)).thenReturn(successProvider(MOCK));
        VideoProviderRouter router = new VideoProviderRouter(ctx, environmentWithPreferred(AGNES), null);

        RuntimeException thrown = assertThrows(RuntimeException.class, () -> router.submit(shot(), 5));
        assertTrue(thrown.getMessage().contains("所有视频通道均失败"));
    }

    @Test
    void providerForUnknownNameThrowsIllegalArgumentException() {
        VideoProviderRouter router = new VideoProviderRouter(contextWithAll(), environmentWithPreferred(AGNES), null);

        assertThrows(IllegalArgumentException.class, () -> router.providerFor("unknown"));
    }

    @Test
    void shotPreferredProviderTakesPriority() {
        ShotVideoRouter shotRouter = mock(ShotVideoRouter.class);
        Shot s = shot();
        when(shotRouter.route(s)).thenReturn(DOUBAO);
        VideoProviderRouter router = new VideoProviderRouter(contextWithAll(), environmentWithPreferred(AGNES), shotRouter);

        // 分镜首选 doubao 应排在链首
        assertEquals(DOUBAO, router.chain(s).get(0));
    }
}
