package com.dramafactory.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 测试替身：位于 {@link LlmScriptService} 同包，重写包可见方法
 * {@code ModelCallResult callModelWithUsage(ObjectNode body)}，
 * 从而真正拦截 MvLyricsService.generate 触发的模型调用。
 */
public class RecordingLlmScriptService extends LlmScriptService {

    public RecordingLlmScriptService() {
        // credentialResolver 传 null 无妨：包可见方法已被重写，不再进入父类方法体
        super(null, new ObjectMapper(), false, "test", 100, 10, 0, "", null);
    }

    public final AtomicReference<LlmScriptService.ModelCallResult> nextResult = new AtomicReference<>();
    public final AtomicReference<RuntimeException> nextFailure = new AtomicReference<>();
    public final AtomicInteger callCount = new AtomicInteger(0);
    public final AtomicReference<JsonNode> lastRequest = new AtomicReference<>();
    public final AtomicReference<CountDownLatch> gate = new AtomicReference<>();

    @Override
    ModelCallResult callModelWithUsage(ObjectNode body) {
        lastRequest.set(body);
        callCount.incrementAndGet();
        CountDownLatch latch = gate.get();
        if (latch != null) {
            try {
                latch.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("被中断", e);
            }
        }
        RuntimeException failure = nextFailure.get();
        if (failure != null) {
            throw failure;
        }
        LlmScriptService.ModelCallResult result = nextResult.get();
        if (result == null) {
            throw new IllegalStateException("测试未设置返回结果");
        }
        return result;
    }
}
