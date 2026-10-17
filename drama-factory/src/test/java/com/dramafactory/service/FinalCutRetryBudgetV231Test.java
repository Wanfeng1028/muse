package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;

import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * v2.31 退避预算的单元测试。
 * 覆盖 claimRetryBackoff 纯函数语义，以及 withFfmpegRetry 的预算/睡眠行为。
 */
class FinalCutRetryBudgetV231Test {

    @TempDir
    Path tempDir;

    // ---------- claimRetryBackoff 纯函数 ----------

    @Test
    void claimEnough() {
        AtomicLong budget = new AtomicLong(2500L);
        long claimed = FinalCutService.claimRetryBackoff(budget, 2000L);
        assertEquals(2000L, claimed);
        assertEquals(500L, budget.get());
    }

    @Test
    void claimTruncated() {
        AtomicLong budget = new AtomicLong(500L);
        long claimed = FinalCutService.claimRetryBackoff(budget, 4000L);
        assertEquals(500L, claimed);
        assertEquals(0L, budget.get());
    }

    @Test
    void claimExhausted() {
        AtomicLong budget = new AtomicLong(0L);
        long claimed = FinalCutService.claimRetryBackoff(budget, 2000L);
        assertEquals(0L, claimed);
        assertEquals(0L, budget.get());
    }

    @Test
    void claimNonPositive() {
        AtomicLong budget = new AtomicLong(1000L);
        assertEquals(0L, FinalCutService.claimRetryBackoff(budget, 0L));
        assertEquals(1000L, budget.get());
        assertEquals(0L, FinalCutService.claimRetryBackoff(budget, -10L));
        assertEquals(1000L, budget.get());
    }

    // ---------- withFfmpegRetry 行为 ----------

    @Test
    void zeroBudgetNoSleep() throws Exception {
        FinalCutService service = newService(3, 2000L, 0L);
        AtomicInteger calls = new AtomicInteger();
        FfmpegService.FfmpegException thrown = new FfmpegService.FfmpegException(
                "boom", new IOException("sim"), true);
        Object step = newThrowingStep(calls, thrown);

        AtomicLong budget = new AtomicLong(0L);
        long start = System.nanoTime();
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> invokeWithFfmpegRetry(service, "op", step, budget));
        long elapsedMs = (System.nanoTime() - start) / 1_000_000L;

        assertEquals("boom", ex.getMessage());
        assertEquals(3, calls.get(), "尝试次数不受预算影响");
        assertTrue(elapsedMs < 2000L, "零预算不应睡眠，耗时: " + elapsedMs);
    }

    @Test
    @Timeout(value = 60, unit = TimeUnit.SECONDS)
    void budgetCapsTotalSleep() throws Exception {
        FinalCutService service = newService(5, 2000L, 2500L);
        AtomicInteger calls = new AtomicInteger();
        FfmpegService.FfmpegException thrown = new FfmpegService.FfmpegException(
                "boom", new IOException("sim"), true);
        Object step = newThrowingStep(calls, thrown);

        AtomicLong budget = new AtomicLong(2500L);
        long start = System.nanoTime();
        assertThrows(FfmpegService.FfmpegException.class,
                () -> invokeWithFfmpegRetry(service, "op", step, budget));
        long elapsedMs = (System.nanoTime() - start) / 1_000_000L;

        assertEquals(5, calls.get(), "应尝试 5 次");
        assertTrue(elapsedMs >= 2300L, "实际睡了 2500ms，耗时下界，实际: " + elapsedMs);
        assertTrue(elapsedMs < 20000L, "耗时上界，实际: " + elapsedMs);
    }

    @Test
    void permanentNoBudgetDeduction() throws Exception {
        FinalCutService service = newService(3, 2000L, 10000L);
        AtomicInteger calls = new AtomicInteger();
        FfmpegService.FfmpegException thrown = new FfmpegService.FfmpegException(
                "perm", new IOException("sim"), false);
        Object step = newThrowingStep(calls, thrown);

        AtomicLong budget = new AtomicLong(10000L);
        assertThrows(FfmpegService.FfmpegException.class,
                () -> invokeWithFfmpegRetry(service, "op", step, budget));

        assertEquals(1, calls.get(), "永久失败不重试");
        assertEquals(10000L, budget.get(), "永久失败不扣预算");
    }

    // ---------- helpers ----------

    private FinalCutService newService(int attempts, long backoffMs, long budgetMs) {
        return new FinalCutService(
                Mockito.mock(FinalCutRepository.class),
                Mockito.mock(EpisodeRepository.class),
                Mockito.mock(ShotRepository.class),
                Mockito.mock(VideoTaskRepository.class),
                Mockito.mock(SubtitleService.class),
                Mockito.mock(FfmpegService.class),
                Mockito.mock(EpisodeStatusFlowService.class),
                tempDir.toString(),
                Mockito.mock(DramaMetrics.class),
                attempts,
                backoffMs,
                budgetMs);
    }

    /**
     * 通过反射调用 private 的 withFfmpegRetry(String, FfmpegStep, AtomicLong)。
     */
    private static Object invokeWithFfmpegRetry(FinalCutService service, String op,
                                                Object step, AtomicLong budget) throws Exception {
        Class<?> stepIf = Class.forName("com.dramafactory.service.FinalCutService$FfmpegStep");
        Method m = FinalCutService.class.getDeclaredMethod("withFfmpegRetry", String.class, stepIf, AtomicLong.class);
        m.setAccessible(true);
        try {
            return m.invoke(service, op, step, budget);
        } catch (java.lang.reflect.InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause instanceof Exception ex) {
                throw ex;
            }
            throw e;
        }
    }

    /**
     * 用动态代理实现 private 的 FfmpegStep 接口，每次调用计数并抛出指定异常。
     */
    private static Object newThrowingStep(AtomicInteger calls, FfmpegService.FfmpegException thrown) throws Exception {
        Class<?> stepIf = Class.forName("com.dramafactory.service.FinalCutService$FfmpegStep");
        assertNotNull(stepIf);
        InvocationHandler handler = (proxy, method, args) -> {
            if ("run".equals(method.getName())) {
                calls.incrementAndGet();
                throw thrown;
            }
            if ("toString".equals(method.getName())) {
                return "throwingStep";
            }
            if ("hashCode".equals(method.getName())) {
                return System.identityHashCode(proxy);
            }
            if ("equals".equals(method.getName())) {
                return proxy == args[0];
            }
            return null;
        };
        return Proxy.newProxyInstance(FinalCutRetryBudgetV231Test.class.getClassLoader(),
                new Class<?>[]{stepIf}, handler);
    }
}
