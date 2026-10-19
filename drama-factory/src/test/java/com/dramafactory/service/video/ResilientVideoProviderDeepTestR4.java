package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ResilientVideoProviderDeepTestR4 {

    private VideoProvider delegate() {
        return mock(VideoProvider.class);
    }

    private CircuitBreakerRegistry cbRegistry() {
        return CircuitBreakerRegistry.ofDefaults();
    }

    private TimeLimiterRegistry tlRegistry() {
        return TimeLimiterRegistry.ofDefaults();
    }

    private ResilientVideoProvider build(VideoProvider delegate, CircuitBreakerRegistry cb, TimeLimiterRegistry tl) {
        return new ResilientVideoProvider(delegate, cb, tl);
    }

    private ResilientVideoProvider build(VideoProvider delegate) {
        return build(delegate, cbRegistry(), tlRegistry());
    }

    private static final class RateLimitedException extends RuntimeException {
        private final int retryAfterSeconds;

        private RateLimitedException(String message, int retryAfterSeconds) {
            super(message);
            this.retryAfterSeconds = retryAfterSeconds;
        }

        private int getRetryAfterSeconds() {
            return retryAfterSeconds;
        }
    }

    @Test
    void name_returnsAgnes() {
        ResilientVideoProvider provider = build(delegate());
        assertEquals("agnes", provider.name());
    }

    @Test
    void submit_delegateOk_returnsId() {
        VideoProvider delegate = delegate();
        when(delegate.submit(any(), anyInt())).thenReturn("agnes-1");
        ResilientVideoProvider provider = build(delegate);
        Shot shot = new Shot();
        String result = provider.submit(shot, 5);
        assertEquals("agnes-1", result);
        verify(delegate, times(1)).submit(any(), anyInt());
    }

    @Test
    void poll_delegateOk_returnsResult() {
        VideoProvider delegate = delegate();
        VideoProvider.ProbeResult probeResult =
                new VideoProvider.ProbeResult(VideoProvider.RemoteStatus.COMPLETED, "http://x", null, 100);
        when(delegate.poll("task-1")).thenReturn(probeResult);
        ResilientVideoProvider provider = build(delegate);
        VideoProvider.ProbeResult result = provider.poll("task-1");
        assertSame(probeResult, result);
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertEquals("http://x", result.videoUrl());
        assertEquals(100, result.progress());
    }

    @Test
    void submit_rateLimited_passthrough() {
        VideoProvider delegate = delegate();
        RateLimitedException rateLimited = new RateLimitedException("限流", 10);
        when(delegate.submit(any(), anyInt())).thenThrow(rateLimited);
        ResilientVideoProvider provider = build(delegate);
        RateLimitedException thrown =
                assertThrows(RateLimitedException.class, () -> provider.submit(new Shot(), 5));
        assertSame(rateLimited, thrown);
        assertEquals("限流", thrown.getMessage());
        assertEquals(10, thrown.getRetryAfterSeconds());
    }

    @Test
    void poll_runtimeException_passthrough() {
        VideoProvider delegate = delegate();
        when(delegate.poll("task-2")).thenThrow(new IllegalStateException("boom"));
        ResilientVideoProvider provider = build(delegate);
        IllegalStateException thrown =
                assertThrows(IllegalStateException.class, () -> provider.poll("task-2"));
        assertEquals("boom", thrown.getMessage());
    }

    @Test
    void probeConnectivity_delegatesDirectly() {
        VideoProvider delegate = delegate();
        VideoProvider.ConnectivityResult connectivity =
                new VideoProvider.ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED, "bad key");
        when(delegate.probeConnectivity()).thenReturn(connectivity);
        ResilientVideoProvider provider = build(delegate);
        VideoProvider.ConnectivityResult result = provider.probeConnectivity();
        assertSame(connectivity, result);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
        verify(delegate, times(1)).probeConnectivity();
    }

    @Test
    void circuitOpen_submit_throwsProviderCircuitOpenException() {
        VideoProvider delegate = delegate();
        CircuitBreakerRegistry cb = cbRegistry();
        cb.circuitBreaker("agnes").transitionToOpenState();
        ResilientVideoProvider provider = build(delegate, cb, tlRegistry());
        ProviderCircuitOpenException thrown =
                assertThrows(ProviderCircuitOpenException.class, () -> provider.submit(new Shot(), 5));
        assertEquals("agnes 熔断器打开，请求被拒绝", thrown.getMessage());
    }

    @Test
    void circuitOpen_poll_alsoThrows() {
        VideoProvider delegate = delegate();
        CircuitBreakerRegistry cb = cbRegistry();
        cb.circuitBreaker("agnes").transitionToOpenState();
        ResilientVideoProvider provider = build(delegate, cb, tlRegistry());
        ProviderCircuitOpenException thrown =
                assertThrows(ProviderCircuitOpenException.class, () -> provider.poll("task-3"));
        assertEquals("agnes 熔断器打开，请求被拒绝", thrown.getMessage());
    }

    @Test
    void circuitOpen_doesNotCallDelegate() {
        VideoProvider delegate = delegate();
        CircuitBreakerRegistry cb = cbRegistry();
        cb.circuitBreaker("agnes").transitionToOpenState();
        ResilientVideoProvider provider = build(delegate, cb, tlRegistry());
        assertThrows(ProviderCircuitOpenException.class, () -> provider.submit(new Shot(), 5));
        verify(delegate, never()).submit(any(), anyInt());
    }

    @Test
    void delegateCheckedException_wrapped() {
        VideoProvider delegate = delegate();
        doAnswer(invocation -> {
            throw new IOException("io-down");
        }).when(delegate).submit(any(), anyInt());
        ResilientVideoProvider provider = build(delegate);
        RuntimeException thrown =
                assertThrows(RuntimeException.class, () -> provider.submit(new Shot(), 5));
        assertEquals("agnes 调用失败", thrown.getMessage());
        assertNotNull(thrown.getCause());
        Throwable cursor = thrown.getCause();
        boolean hasIo = false;
        while (cursor != null) {
            if (cursor instanceof IOException) {
                hasIo = true;
                break;
            }
            cursor = cursor.getCause();
        }
        assertTrue(hasIo);
    }

    @Test
    void submit_nullShot_delegates() {
        VideoProvider delegate = delegate();
        when(delegate.submit(null, 5)).thenReturn("agnes-null");
        ResilientVideoProvider provider = build(delegate);
        String result = provider.submit(null, 5);
        assertEquals("agnes-null", result);
        verify(delegate, times(1)).submit(null, 5);
    }

    @Test
    void registries_isolatedPerCase() {
        VideoProvider delegate1 = delegate();
        CircuitBreakerRegistry cb1 = cbRegistry();
        TimeLimiterRegistry tl1 = tlRegistry();
        cb1.circuitBreaker("agnes").transitionToOpenState();
        ResilientVideoProvider provider1 = build(delegate1, cb1, tl1);
        assertThrows(ProviderCircuitOpenException.class, () -> provider1.submit(new Shot(), 5));

        VideoProvider delegate2 = delegate();
        when(delegate2.submit(any(), anyInt())).thenReturn("agnes-2");
        ResilientVideoProvider provider2 = build(delegate2, cbRegistry(), tlRegistry());
        assertEquals("agnes-2", provider2.submit(new Shot(), 5));
    }

    @Test
    void circuitOpen_providerCircuitOpenException_causeIsCallNotPermitted() {
        VideoProvider delegate = delegate();
        CircuitBreakerRegistry cb = cbRegistry();
        cb.circuitBreaker("agnes").transitionToOpenState();
        ResilientVideoProvider provider = build(delegate, cb, tlRegistry());
        ProviderCircuitOpenException thrown =
                assertThrows(ProviderCircuitOpenException.class, () -> provider.submit(new Shot(), 5));
        assertNotNull(thrown.getCause());
        assertTrue(thrown.getCause() instanceof io.github.resilience4j.circuitbreaker.CallNotPermittedException);
    }
}