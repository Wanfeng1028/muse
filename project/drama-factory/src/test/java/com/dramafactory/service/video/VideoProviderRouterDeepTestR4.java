package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class VideoProviderRouterDeepTestR4 {

    private ApplicationContext applicationContext;
    private Environment environment;
    private ShotVideoRouter shotVideoRouter;
    private VideoProviderRouter router;

    @BeforeEach
    void setUp() {
        applicationContext = mock(ApplicationContext.class);
        environment = mock(Environment.class);
        shotVideoRouter = mock(ShotVideoRouter.class);
        router = new VideoProviderRouter(applicationContext, environment, shotVideoRouter);
    }

    @Test
    void chain_blankPreferred_returnsMockOnly() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("  ");
        assertEquals(List.of("mock"), router.chain());
    }

    @Test
    void chain_nullPreferred_returnsMockOnly() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn(null);
        assertEquals(List.of("mock"), router.chain());
    }

    @Test
    void chain_novaiPreferred_order() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("novai");
        assertEquals(List.of("novai", "agnes", "minimax", "doubao", "htmlrender", "painted"), router.chain());
    }

    @Test
    void chain_paintedPreferred_noDuplicate() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("painted");
        assertEquals(List.of("painted", "agnes", "minimax", "novai", "doubao", "htmlrender"), router.chain());
    }

    @Test
    void chain_shot_mockPreferred_ignoresShot() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("mock");
        Shot shot = new Shot();
        assertEquals(List.of("mock"), router.chain(shot));
    }

    @Test
    void chain_shot_noShotPreferred() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        Shot shot = new Shot();
        when(shotVideoRouter.route(shot)).thenReturn(null);
        assertEquals(List.of("agnes", "minimax", "novai", "doubao", "htmlrender", "painted"), router.chain(shot));
    }

    @Test
    void chain_shot_preferredDedup() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        Shot shot = new Shot();
        when(shotVideoRouter.route(shot)).thenReturn("novai");
        assertEquals(List.of("novai", "agnes", "minimax", "doubao", "htmlrender", "painted"), router.chain(shot));
    }

    @Test
    void providerFor_qwen_beanName() {
        VideoProvider provider = mock(VideoProvider.class);
        when(applicationContext.getBean("qwenVideoProvider", VideoProvider.class)).thenReturn(provider);
        assertEquals(provider, router.providerFor("qwen"));
        verify(applicationContext).getBean("qwenVideoProvider", VideoProvider.class);
    }

    @Test
    void providerFor_htmlrender_beanName() {
        VideoProvider provider = mock(VideoProvider.class);
        when(applicationContext.getBean("htmlRenderVideoProvider", VideoProvider.class)).thenReturn(provider);
        assertEquals(provider, router.providerFor("htmlrender"));
        verify(applicationContext).getBean("htmlRenderVideoProvider", VideoProvider.class);
    }

    @Test
    void providerFor_unknown_messageContainsName() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> router.providerFor("xxx"));
        assertEquals("未知视频通道：xxx", ex.getMessage());
    }

    @Test
    void submit_firstSuccess_noFallbackReason() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("mock");
        VideoProvider mockProvider = mock(VideoProvider.class);
        when(applicationContext.getBean("mockVideoProvider", VideoProvider.class)).thenReturn(mockProvider);
        Shot shot = new Shot();
        when(mockProvider.submit(shot, 5)).thenReturn("t-1");

        VideoProviderRouter.RouteResult result = router.submit(shot, 5);

        assertEquals("mock", result.providerName());
        assertEquals("t-1", result.providerTaskId());
        assertNull(result.fallbackReason());
        assertNull(router.lastFallback());
    }

    @Test
    void submit_secondSuccess_recordsLastFallback() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProvider agnes = mock(VideoProvider.class);
        VideoProvider minimax = mock(VideoProvider.class);
        VideoProvider novai = mock(VideoProvider.class);
        when(applicationContext.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(applicationContext.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);
        when(applicationContext.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(novai);
        Shot shot = new Shot();
        when(agnes.submit(shot, 5)).thenThrow(new RateLimitedException("限流", 30));
        when(minimax.submit(shot, 5)).thenThrow(new RateLimitedException("限流", 30));
        when(novai.submit(shot, 5)).thenReturn("t-2");

        VideoProviderRouter.RouteResult result = router.submit(shot, 5);

        assertEquals("novai", result.providerName());
        assertEquals("t-2", result.providerTaskId());
        assertEquals("限流(429)，30秒后可重试", result.fallbackReason());
        assertEquals("agnes", router.lastFallback().from());
        assertEquals("novai", router.lastFallback().to());
        assertEquals("限流(429)，30秒后可重试", router.lastFallback().reason());
    }

    @Test
    void submit_timeoutReason() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProvider agnes = mock(VideoProvider.class);
        VideoProvider minimax = mock(VideoProvider.class);
        VideoProvider novai = mock(VideoProvider.class);
        when(applicationContext.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(applicationContext.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);
        when(applicationContext.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(novai);
        Shot shot = new Shot();
        when(agnes.submit(shot, 5)).thenThrow(new RuntimeException("调用超时，请重试"));
        when(minimax.submit(shot, 5)).thenThrow(new RuntimeException("调用超时，请重试"));
        when(novai.submit(shot, 5)).thenReturn("t-3");

        VideoProviderRouter.RouteResult result = router.submit(shot, 5);

        assertEquals("novai", result.providerName());
        assertEquals("t-3", result.providerTaskId());
        assertEquals("调用超时", result.fallbackReason());
    }

    @Test
    void submit_longMessage_truncated100() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProvider agnes = mock(VideoProvider.class);
        VideoProvider minimax = mock(VideoProvider.class);
        VideoProvider novai = mock(VideoProvider.class);
        when(applicationContext.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(applicationContext.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);
        when(applicationContext.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(novai);
        Shot shot = new Shot();
        when(agnes.submit(shot, 5)).thenThrow(new RuntimeException("e".repeat(150)));
        when(minimax.submit(shot, 5)).thenThrow(new RuntimeException("e".repeat(150)));
        when(novai.submit(shot, 5)).thenReturn("t-4");

        VideoProviderRouter.RouteResult result = router.submit(shot, 5);

        assertEquals("novai", result.providerName());
        assertEquals("t-4", result.providerTaskId());
        assertEquals("提交异常：" + "e".repeat(100), result.fallbackReason());
    }

    @Test
    void submit_nullMessage_reason() {
        when(environment.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProvider agnes = mock(VideoProvider.class);
        VideoProvider minimax = mock(VideoProvider.class);
        VideoProvider novai = mock(VideoProvider.class);
        when(applicationContext.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(applicationContext.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);
        when(applicationContext.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(novai);
        Shot shot = new Shot();
        when(agnes.submit(shot, 5)).thenThrow(new RuntimeException((String) null));
        when(minimax.submit(shot, 5)).thenThrow(new RuntimeException((String) null));
        when(novai.submit(shot, 5)).thenReturn("t-5");

        VideoProviderRouter.RouteResult result = router.submit(shot, 5);

        assertEquals("novai", result.providerName());
        assertEquals("t-5", result.providerTaskId());
        assertEquals("提交异常：", result.fallbackReason());
    }
}