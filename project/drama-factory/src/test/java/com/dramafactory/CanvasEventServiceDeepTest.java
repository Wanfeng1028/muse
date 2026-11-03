package com.dramafactory;

import com.dramafactory.service.CanvasEventService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
public class CanvasEventServiceDeepTest {

    @Autowired
    private CanvasEventService canvasEventService;

    @SuppressWarnings("unchecked")
    @FunctionalInterface
    private interface ThrowingBooleanSupplier {
        boolean get() throws Exception;
    }

    private static void awaitCondition(ThrowingBooleanSupplier condition, long timeoutMillis) {
        long deadline = System.currentTimeMillis() + timeoutMillis;
        while (System.currentTimeMillis() < deadline) {
            try {
                if (condition.get()) {
                    return;
                }
            } catch (Exception e) {
                throw new AssertionError("awaitCondition 条件求值抛出异常", e);
            }
            try {
                Thread.sleep(50);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                throw new AssertionError("awaitCondition 被中断", ie);
            }
        }
        throw new AssertionError("awaitCondition 超时未满足条件（" + timeoutMillis + "ms）");
    }

    private CopyOnWriteArrayList<SseEmitter> readEmitters() throws Exception {
        Field field = CanvasEventService.class.getDeclaredField("emitters");
        field.setAccessible(true);
        return (CopyOnWriteArrayList<SseEmitter>) field.get(canvasEventService);
    }

    private void invokeSendEvent(SseEmitter emitter, String name, String json) throws Exception {
        Method method = CanvasEventService.class.getDeclaredMethod("sendEvent", SseEmitter.class, String.class, String.class);
        method.setAccessible(true);
        method.invoke(canvasEventService, emitter, name, json);
    }

    @Test
    public void subscribe_returnsEmitterAndRegistersInList() throws Exception {
        // given: 初始 emitters 列表规模
        int before = readEmitters().size();
        // when: 订阅一个版本号
        SseEmitter emitter = canvasEventService.subscribe(1);
        // then: 返回非空 emitter，且列表数量增加
        assertNotNull(emitter);
        assertEquals(before + 1, readEmitters().size());
    }

    @Test
    public void subscribe_multipleVersions_allRegistered() throws Exception {
        // given: 清空计数基线
        int before = readEmitters().size();
        // when: 连续订阅三个版本
        SseEmitter e1 = canvasEventService.subscribe(1);
        SseEmitter e2 = canvasEventService.subscribe(2);
        SseEmitter e3 = canvasEventService.subscribe(3);
        // then: 三个 emitter 均非空且列表增长 3
        assertNotNull(e1);
        assertNotNull(e2);
        assertNotNull(e3);
        assertEquals(before + 3, readEmitters().size());
    }

    @Test
    public void broadcast_withNullMap_doesNotThrowAndKeepsEmitters() throws Exception {
        // given: 一个已订阅的 emitter
        SseEmitter emitter = canvasEventService.subscribe(1);
        int sizeBefore = readEmitters().size();
        // when: 用 null dataMap 广播
        canvasEventService.broadcast("ping", null);
        // then: 不抛异常，emitter 仍在列表中
        assertTrue(readEmitters().contains(emitter));
        assertEquals(sizeBefore, readEmitters().size());
    }

    @Test
    public void broadcast_withEmptyMap_sendsToAllEmitters() throws Exception {
        // given: 两个已订阅 emitter
        SseEmitter e1 = canvasEventService.subscribe(1);
        SseEmitter e2 = canvasEventService.subscribe(2);
        int sizeBefore = readEmitters().size();
        // when: 广播空 map
        Map<String, Object> data = new LinkedHashMap<>();
        canvasEventService.broadcast("empty", data);
        // then: 两个 emitter 仍在列表中
        assertTrue(readEmitters().contains(e1));
        assertTrue(readEmitters().contains(e2));
        assertEquals(sizeBefore, readEmitters().size());
    }

    @Test
    public void broadcast_withLargePayload_stillSends() throws Exception {
        // given: 一个已订阅 emitter，构造约 1MB 字符串
        SseEmitter emitter = canvasEventService.subscribe(1);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 10000; i++) {
            sb.append("abcdefghij");
        }
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("blob", sb.toString());
        // when: 广播超大 payload
        canvasEventService.broadcast("large", data);
        // then: emitter 未被移除
        assertTrue(readEmitters().contains(emitter));
        assertNotNull(emitter);
    }

    @Test
    public void broadcast_afterEmitterCompletion_removesFromList() throws Exception {
        // given: 订阅一个 emitter
        SseEmitter emitter = canvasEventService.subscribe(1);
        // when: 用公开 API 触发完成，使回调将其摘除
        emitter.complete();
        // then: 完成回调最终生效，该 emitter 最终不在列表中（避免与 100ms 延迟任务竞态）
        awaitCondition(() -> !readEmitters().contains(emitter), 2000);
        assertFalse(readEmitters().contains(emitter));
    }

    @Test
    public void broadcast_idempotentRepeatedCalls_keepEmitterRegistered() throws Exception {
        // given: 一个订阅 emitter
        SseEmitter emitter = canvasEventService.subscribe(1);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("k", "v");
        // when: 重复广播同一事件名和数据
        canvasEventService.broadcast("tick", data);
        canvasEventService.broadcast("tick", data);
        canvasEventService.broadcast("tick", data);
        // then: emitter 仍在列表中，且没有重复注册
        assertTrue(readEmitters().contains(emitter));
        assertEquals(1, readEmitters().stream().filter(x -> x == emitter).count());
    }

    @Test
    public void concurrentBroadcast_twoThreads_doesNotLoseEmitter() throws Exception {
        // given: 一个订阅 emitter，两个并发广播线程
        SseEmitter emitter = canvasEventService.subscribe(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger errors = new AtomicInteger(0);
        // when: 两线程同时广播
        Runnable task = () -> {
            try {
                start.await();
                Map<String, Object> data = new LinkedHashMap<>();
                data.put("t", Thread.currentThread().getName());
                for (int i = 0; i < 50; i++) {
                    canvasEventService.broadcast("concurrent", data);
                }
            } catch (Throwable t) {
                errors.incrementAndGet();
            }
        };
        pool.submit(task);
        pool.submit(task);
        start.countDown();
        pool.shutdown();
        boolean finished = pool.awaitTermination(10, TimeUnit.SECONDS);
        // then: 无错误、线程正常结束、emitter 仍存在
        assertTrue(finished);
        assertEquals(0, errors.get());
        assertTrue(readEmitters().contains(emitter));
    }

    @Test
    public void concurrentSubscribe_tenThreads_allRegistered() throws Exception {
        // given: 10 个并发订阅线程
        int before = readEmitters().size();
        ExecutorService pool = Executors.newFixedThreadPool(10);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger count = new AtomicInteger(0);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        // when: 并发订阅
        for (int i = 0; i < 10; i++) {
            final int v = i;
            pool.submit(() -> {
                try {
                    start.await();
                    SseEmitter e = canvasEventService.subscribe(v);
                    if (e != null) {
                        count.incrementAndGet();
                    }
                } catch (Throwable t) {
                    failure.set(t);
                }
            });
        }
        start.countDown();
        pool.shutdown();
        boolean finished = pool.awaitTermination(10, TimeUnit.SECONDS);
        // then: 全部成功、列表增长 10、无异常
        assertTrue(finished);
        assertEquals(10, count.get());
        assertEquals(before + 10, readEmitters().size());
        assertEquals(null, failure.get());
    }

    @Test
    public void sendEvent_onClosedEmitter_removesFromList() throws Exception {
        // given: 订阅一个 emitter，随后用公开 API complete() 触发完成回调将其摘除
        SseEmitter emitter = canvasEventService.subscribe(1);
        emitter.complete();
        // 等待完成回调先执行，把该 emitter 从列表摘除（最终一致性）
        awaitCondition(() -> !readEmitters().contains(emitter), 2000);
        // when: 通过反射直接调用 sendEvent 给已关闭的 emitter
        invokeSendEvent(emitter, "name", "{\"a\":1}");
        // then: 发送失败不应导致列表异常增长，且该 emitter 始终不在列表中
        awaitCondition(() -> !readEmitters().contains(emitter), 2000);
        // 稳定性复核：再等一轮竞态窗口，列表内容不应因本次 sendEvent 而增加
        int sizeNow = readEmitters().size();
        invokeSendEvent(emitter, "name", "{\"a\":1}");
        awaitCondition(() -> readEmitters().size() <= sizeNow, 2000);
        assertFalse(readEmitters().contains(emitter));
    }

    @Test
    public void subscribe_completionCallbackRemovesEmitter() throws Exception {
        // given: 一个订阅 emitter，注册完成回调
        SseEmitter emitter = canvasEventService.subscribe(1);
        // when: 用公开 API 触发完成
        emitter.complete();
        // then: 回调最终生效，该 emitter 最终不在列表中（轮询等待，避免与 100ms 延迟任务竞态）
        awaitCondition(() -> !readEmitters().contains(emitter), 2000);
        assertFalse(readEmitters().contains(emitter));
    }

    @Test
    public void subscribe_completionAndErrorCallbacksRemoveEmitter() throws Exception {
        // given: subscribe 的 version 参数是协议版本，不是超时（服务内硬编码 30 分钟超时，测试无法等待）；
        // 这里验证可真实触发的 onCompletion / onError 回调能摘除 emitter（onTimeout 注册的是同一模式）
        SseEmitter emitter = canvasEventService.subscribe(1);
        assertTrue(readEmitters().contains(emitter), "订阅后 emitter 应在列表中");

        // when: 触发 completion 回调
        emitter.complete();

        // then: emitter 被摘除
        awaitCondition(() -> !readEmitters().contains(emitter), 2000);
        assertFalse(readEmitters().contains(emitter), "complete 后 emitter 应被摘除");

        // when: 另一个 emitter 触发 error 回调
        SseEmitter errorEmitter = canvasEventService.subscribe(1);
        errorEmitter.completeWithError(new RuntimeException("测试错误"));

        // then: emitter 被摘除
        awaitCondition(() -> !readEmitters().contains(errorEmitter), 2000);
        assertFalse(readEmitters().contains(errorEmitter), "error 后 emitter 应被摘除");
    }

    @Test
    public void broadcast_isolatedByCompletion_noCrossContamination() throws Exception {
        // given: 两个订阅 emitter，一个完成后另一个应保留
        SseEmitter keep = canvasEventService.subscribe(1);
        SseEmitter gone = canvasEventService.subscribe(2);
        // when: 只完成 gone
        gone.complete();
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("x", 1);
        canvasEventService.broadcast("iso", data);
        // then: keep 仍在，gone 已移除
        assertTrue(readEmitters().contains(keep));
        assertFalse(readEmitters().contains(gone));
    }

    @Test
    public void broadcast_emptyEmitters_noOp() throws Exception {
        // given: 清空 emitters 列表
        readEmitters().clear();
        int sizeBefore = readEmitters().size();
        // when: 广播到空列表
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("n", 1);
        canvasEventService.broadcast("nobody", data);
        // then: 列表仍为空，不抛异常
        assertEquals(0, sizeBefore);
        assertEquals(0, readEmitters().size());
    }

    @Test
    public void subscribe_sameEmitterInstanceDistinctPerCall() throws Exception {
        // given: 两次独立订阅
        SseEmitter a = canvasEventService.subscribe(1);
        SseEmitter b = canvasEventService.subscribe(1);
        // when: 比较两个返回对象
        // then: 每次订阅返回不同实例
        assertNotNull(a);
        assertNotNull(b);
        assertFalse(a == b);
        assertSame(a, a);
    }
}