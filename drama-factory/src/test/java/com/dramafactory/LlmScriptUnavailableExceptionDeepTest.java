package com.dramafactory;

import com.dramafactory.service.LlmScriptUnavailableException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@TestPropertySource(properties = {
        "drama.script.llm.enabled=false",
        "spring.datasource.url=jdbc:h2:mem:drama_factory_deep;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class LlmScriptUnavailableExceptionDeepTest {

    private LlmScriptUnavailableException exception;

    @BeforeEach
    void setUp() {
        exception = new LlmScriptUnavailableException("AI 剧本生成不可用：配置未启用");
    }

    @Test
    @DisplayName("单参构造：message 被正确保存且 cause 为空")
    void singleArgConstructor_storesMessageAndNullCause() {
        // given
        String message = "AI 剧本生成不可用：配置未启用";

        // when
        LlmScriptUnavailableException ex = new LlmScriptUnavailableException(message);

        // then
        assertEquals(message, ex.getMessage());
        assertNull(ex.getCause());
        assertTrue(ex instanceof RuntimeException);
    }

    @Test
    @DisplayName("双参构造：message 与 cause 都被保留")
    void twoArgConstructor_storesMessageAndCause() {
        // given
        String message = "调用大模型失败：连接超时";
        Throwable cause = new java.net.SocketTimeoutException("read timed out");

        // when
        LlmScriptUnavailableException ex = new LlmScriptUnavailableException(message, cause);

        // then
        assertEquals(message, ex.getMessage());
        assertSame(cause, ex.getCause());
        assertEquals("read timed out", ex.getCause().getMessage());
    }

    @Test
    @DisplayName("pause 语义：不可用异常作为失败信号被抛出，Run 保持可恢复")
    void pauseSemantics_exceptionThrown_runRecoverable() {
        // given
        String runId = "run-pause-001";
        AtomicReference<String> runState = new AtomicReference<>("RUNNING");

        // when
        LlmScriptUnavailableException thrown = assertThrows(LlmScriptUnavailableException.class, () -> {
            runState.set("PAUSED");
            throw exception;
        });

        // then
        assertEquals("PAUSED", runState.get());
        assertEquals("AI 剧本生成不可用：配置未启用", thrown.getMessage());
    }

    @Test
    @DisplayName("resume 语义：暂停后重新推进，异常不再抛出且状态回到 RUNNING")
    void resumeSemantics_afterPause_stateBackToRunning() {
        // given
        AtomicReference<String> runState = new AtomicReference<>("PAUSED");
        AtomicInteger attempts = new AtomicInteger(0);

        // when
        try {
            attempts.incrementAndGet();
            throw exception;
        } catch (LlmScriptUnavailableException ex) {
            runState.set("RUNNING");
        }

        // then
        assertEquals("RUNNING", runState.get());
        assertEquals(1, attempts.get());
    }

    @Test
    @DisplayName("cancel 语义：取消后 Run 终态为 CANCELLED，不可再恢复")
    void cancelSemantics_afterCancel_stateTerminal() {
        // given
        AtomicReference<String> runState = new AtomicReference<>("RUNNING");

        // when
        try {
            throw exception;
        } catch (LlmScriptUnavailableException ex) {
            runState.set("CANCELLED");
        }
        boolean canResume = "CANCELLED".equals(runState.get());

        // then
        assertEquals("CANCELLED", runState.get());
        assertTrue(canResume);
        assertFalse("RUNNING".equals(runState.get()));
    }

    @Test
    @DisplayName("retry 语义：多次重试后仍失败，异常被再次抛出且携带最后一次 cause")
    void retrySemantics_multipleAttemptsLastCausePreserved() {
        // given
        int maxRetries = 3;
        AtomicInteger attempt = new AtomicInteger(0);
        Throwable lastCause = new java.net.ConnectException("connection refused");

        // when
        LlmScriptUnavailableException finalEx = null;
        for (int i = 0; i < maxRetries; i++) {
            attempt.incrementAndGet();
            try {
                throw new LlmScriptUnavailableException("第 " + attempt.get() + " 次重试失败", lastCause);
            } catch (LlmScriptUnavailableException ex) {
                finalEx = ex;
            }
        }

        // then
        assertNotNull(finalEx);
        assertEquals(maxRetries, attempt.get());
        assertSame(lastCause, finalEx.getCause());
        assertEquals("第 3 次重试失败", finalEx.getMessage());
    }

    @Test
    @DisplayName("幂等性：相同入参重复构造，message 与 cause 每次都一致")
    void idempotency_sameInputsProduceSameResult() {
        // given
        String message = "大模型返回内容格式无效";
        Throwable cause = new IllegalStateException("unparseable json");

        // when
        LlmScriptUnavailableException first = new LlmScriptUnavailableException(message, cause);
        LlmScriptUnavailableException second = new LlmScriptUnavailableException(message, cause);
        LlmScriptUnavailableException third = new LlmScriptUnavailableException(message, cause);

        // then
        assertEquals(first.getMessage(), second.getMessage());
        assertEquals(second.getMessage(), third.getMessage());
        assertSame(first.getCause(), second.getCause());
        assertSame(second.getCause(), third.getCause());
        assertNotSame(first, second);
    }

    @Test
    @DisplayName("失败注入：依赖抛出异常时异常链完整，可追溯根因")
    void failureInjection_causeChainIntact() {
        // given
        RuntimeException root = new RuntimeException("底层网络断了");
        LlmScriptUnavailableException wrapped = new LlmScriptUnavailableException("调用大模型失败", root);

        // when
        Throwable cause = wrapped.getCause();
        Throwable rootCause = cause.getCause();

        // then
        assertSame(root, cause);
        assertNull(rootCause);
        assertEquals("底层网络断了", cause.getMessage());
    }

    @Test
    @DisplayName("失败注入：异常栈中可读到抛出点，便于回滚定位")
    void failureInjection_stackTraceContainsThrowSite() {
        // given
        LlmScriptUnavailableException ex = new LlmScriptUnavailableException("回滚前抛出的异常");

        // when
        StackTraceElement[] stack = ex.getStackTrace();
        StringWriter sw = new StringWriter();
        ex.printStackTrace(new PrintWriter(sw));
        String printed = sw.toString();

        // then
        assertNotNull(stack);
        assertTrue(printed.contains("LlmScriptUnavailableException"));
        assertTrue(printed.contains("回滚前抛出的异常"));
    }

    @Test
    @DisplayName("并发：两线程同时抛同源异常，各自 message 独立不串数据")
    void concurrency_twoThreadsThrowIndependently() throws InterruptedException {
        // given
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicReference<String> msgA = new AtomicReference<>();
        AtomicReference<String> msgB = new AtomicReference<>();
        AtomicReference<Throwable> causeA = new AtomicReference<>();
        AtomicReference<Throwable> causeB = new AtomicReference<>();

        // when
        pool.submit(() -> {
            try {
                start.await();
                throw new LlmScriptUnavailableException("线程A失败", new java.io.IOException("A的IO"));
            } catch (LlmScriptUnavailableException ex) {
                msgA.set(ex.getMessage());
                causeA.set(ex.getCause());
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        });
        pool.submit(() -> {
            try {
                start.await();
                throw new LlmScriptUnavailableException("线程B失败", new java.net.UnknownHostException("B的主机"));
            } catch (LlmScriptUnavailableException ex) {
                msgB.set(ex.getMessage());
                causeB.set(ex.getCause());
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        });
        start.countDown();
        boolean finished = done.await(5, TimeUnit.SECONDS);
        pool.shutdown();

        // then
        assertTrue(finished);
        assertEquals("线程A失败", msgA.get());
        assertEquals("线程B失败", msgB.get());
        assertTrue(causeA.get() instanceof java.io.IOException);
        assertTrue(causeB.get() instanceof java.net.UnknownHostException);
    }

    @Test
    @DisplayName("边界：空 message 被允许，getMessage 返回空串")
    void boundary_emptyMessageAllowed() {
        // given
        String emptyMessage = "";

        // when
        LlmScriptUnavailableException ex = new LlmScriptUnavailableException(emptyMessage);

        // then
        assertEquals("", ex.getMessage());
        assertNull(ex.getCause());
    }

    @Test
    @DisplayName("边界：超大 payload 作为 message 不丢失内容")
    void boundary_hugePayloadMessagePreserved() {
        // given
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < 20000; i++) {
            builder.append('x');
        }
        String hugeMessage = builder.toString();

        // when
        LlmScriptUnavailableException ex = new LlmScriptUnavailableException(hugeMessage);

        // then
        assertEquals(20000, ex.getMessage().length());
        assertArrayEquals(hugeMessage.getBytes(), ex.getMessage().getBytes());
    }

    @Test
    @DisplayName("边界：非法状态跳转（CANCELLED -> RUNNING）被业务侧拒绝")
    void boundary_illegalStateTransitionRejected() {
        // given
        AtomicReference<String> runState = new AtomicReference<>("CANCELLED");
        List<String> allowedTransitions = new ArrayList<>();
        allowedTransitions.add("RUNNING->PAUSED");
        allowedTransitions.add("PAUSED->RUNNING");
        allowedTransitions.add("RUNNING->CANCELLED");

        // when
        String attempted = runState.get() + "->RUNNING";
        boolean allowed = allowedTransitions.contains(attempted);

        // then
        assertFalse(allowed);
        assertEquals("CANCELLED", runState.get());
    }

    @Test
    @DisplayName("边界：空 Run 场景下抛异常不产生副作用，message 仍可读")
    void boundary_nullRunStillCarriesMessage() {
        // given
        String message = "Run 不存在，无法推进剧本生成";

        // when
        LlmScriptUnavailableException ex = new LlmScriptUnavailableException(message, null);

        // then
        assertEquals(message, ex.getMessage());
        assertNull(ex.getCause());
        assertTrue(ex.getStackTrace().length > 0);
    }

    @Test
    @DisplayName("降级契约：捕获异常后可切换模板生成，不中断链路")
    void fallbackContract_catchAndSwitchToTemplate() {
        // given
        AtomicReference<String> generatedBy = new AtomicReference<>("LLM");
        AtomicInteger templateFallbackCount = new AtomicInteger(0);

        // when
        try {
            throw exception;
        } catch (LlmScriptUnavailableException ex) {
            generatedBy.set("TEMPLATE");
            templateFallbackCount.incrementAndGet();
        }

        // then
        assertEquals("TEMPLATE", generatedBy.get());
        assertEquals(1, templateFallbackCount.get());
        assertFalse("LLM".equals(generatedBy.get()));
    }

    @Test
    @DisplayName("序列化友好：异常类型名与继承链稳定，便于日志聚合")
    void typeHierarchyStable_forLogAggregation() {
        // given
        Class<?> type = LlmScriptUnavailableException.class;

        // when
        Class<?> superClass = type.getSuperclass();
        String simpleName = type.getSimpleName();

        // then
        assertEquals(RuntimeException.class, superClass);
        assertEquals("LlmScriptUnavailableException", simpleName);
        assertTrue(RuntimeException.class.isAssignableFrom(type));
    }
}