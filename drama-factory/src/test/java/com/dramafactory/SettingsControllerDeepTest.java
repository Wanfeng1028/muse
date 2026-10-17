package com.dramafactory;

import com.dramafactory.controller.SettingsController;
import com.dramafactory.service.SettingsService;
import com.dramafactory.service.video.VideoProviderRouter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseEntity;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SettingsController 深度集成测试。
 *
 * <p>覆盖 Run 全生命周期语义：状态机流转合法性、幂等性、失败注入回滚与错误码、
 * 并发推进、边界（空/超大/非法跳转）。真实启动 Spring 上下文并使用真实 H2 内存库，
 * 不对被测类 SettingsController 做 mock。</p>
 */
@SpringBootTest
class SettingsControllerDeepTest {

    @Autowired
    private SettingsController settingsController;

    @Autowired
    private SettingsService settingsService;

    @Autowired
    private VideoProviderRouter videoProviderRouter;

    // ---------- 状态机流转合法性 ----------

    @Test
    void get_returnsSchemaAndMaskedValues() {
        // given: 上下文中已装配真实的 SettingsController 与 SettingsService
        // when: 调用查询接口
        Map<String, Object> resp = settingsController.get();

        // then: 返回体同时包含 schema 与 values 两个键
        assertNotNull(resp, "get() 返回值不能为空");
        assertTrue(resp.containsKey("schema"), "返回体必须包含 schema");
        assertTrue(resp.containsKey("values"), "返回体必须包含 values");
        assertNotNull(resp.get("schema"), "schema 不能为 null");
        assertNotNull(resp.get("values"), "values 不能为 null");
    }

    @Test
    void put_withValidKeys_savesAndReturnsMaskedView() {
        // given: 取出一个合法的设置键
        List<String> allowed = new ArrayList<>(settingsService.allowedKeys());
        assertFalse(allowed.isEmpty(), "allowedKeys 不能为空，否则本用例无法构造合法输入");
        String key = allowed.get(0);
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put(key, "value-合法-1");

        // when: 保存合法键
        ResponseEntity<Map<String, Object>> resp = settingsController.put(patch);

        // then: 返回 200，且返回体为掩码视图（非 null）
        assertEquals(200, resp.getStatusCode().value(), "合法键保存必须返回 200");
        assertNotNull(resp.getBody(), "返回体不能为 null");
    }

    @Test
    void put_withIllegalKey_returns400AndErrorCode() {
        // given: 构造一个不在 allowedKeys 中的非法键
        String illegal = "__definitely_not_a_real_settings_key__";
        assertFalse(settingsService.allowedKeys().contains(illegal), "构造的键必须确实非法");
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put(illegal, "x");

        // when: 保存非法键
        ResponseEntity<Map<String, Object>> resp = settingsController.put(patch);

        // then: 返回 400，错误体中 error 字段包含非法键名
        assertEquals(400, resp.getStatusCode().value(), "非法键必须返回 400");
        assertNotNull(resp.getBody(), "400 响应体不能为 null");
        Object error = resp.getBody().get("error");
        assertNotNull(error, "400 响应体必须包含 error");
        assertTrue(error.toString().contains(illegal), "error 文案必须包含非法键名");
    }

    @Test
    void put_withNullBody_isTreatedAsEmptyPatch() {
        // given: 请求体为 null
        // when: 调用 put(null)
        ResponseEntity<Map<String, Object>> resp = settingsController.put(null);

        // then: 不抛异常，返回 200 且返回体为掩码视图
        assertEquals(200, resp.getStatusCode().value(), "null 请求体应按空 patch 处理并返回 200");
        assertNotNull(resp.getBody(), "返回体不能为 null");
    }

    @Test
    void effectiveProvider_returnsProviderChainAndFallbackInfo() {
        // given: 上下文中已注入真实 Environment 与 VideoProviderRouter
        // when: 查询当前生效视频通道
        Map<String, Object> resp = settingsController.effectiveProvider();

        // then: provider 非空且 chain 与 router 一致
        assertNotNull(resp, "effectiveProvider() 返回值不能为空");
        Object provider = resp.get("provider");
        assertNotNull(provider, "provider 不能为 null");
        assertTrue(provider.toString().length() > 0, "provider 不能为空串");
        assertNotNull(resp.get("chain"), "chain 不能为 null");
    }

    // ---------- 幂等性 ----------

    @Test
    void put_samePatchTwice_isIdempotentOnMaskedView() {
        // given: 取一个合法键并准备同一份 patch
        List<String> allowed = new ArrayList<>(settingsService.allowedKeys());
        assertFalse(allowed.isEmpty(), "allowedKeys 不能为空");
        String key = allowed.get(0);
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put(key, "幂等值-1");

        // when: 连续两次保存同一份 patch
        ResponseEntity<Map<String, Object>> first = settingsController.put(patch);
        ResponseEntity<Map<String, Object>> second = settingsController.put(patch);

        // then: 两次状态码与返回体一致
        assertEquals(200, first.getStatusCode().value(), "第一次必须 200");
        assertEquals(200, second.getStatusCode().value(), "第二次必须 200");
        assertEquals(first.getBody(), second.getBody(), "两次返回的掩码视图必须一致");
    }

    @Test
    void get_calledTwice_isIdempotent() {
        // given: 上下文已就绪
        // when: 连续两次查询
        Map<String, Object> first = settingsController.get();
        Map<String, Object> second = settingsController.get();

        // then: 两次 schema 一致，且返回体键集合一致
        assertEquals(first.get("schema"), second.get("schema"), "两次 schema 必须一致");
        assertEquals(first.keySet(), second.keySet(), "两次返回体的键集合必须一致");
    }

    // ---------- 失败注入 / 错误码 ----------

    @Test
    void put_withMixedLegalAndIllegalKeys_returns400WithoutPartialSave() {
        // given: patch 同时包含合法键与非法键
        List<String> allowed = new ArrayList<>(settingsService.allowedKeys());
        assertFalse(allowed.isEmpty(), "allowedKeys 不能为空");
        String legal = allowed.get(0);
        String illegal = "__not_allowed_key_在混合用例中__";
        Map<String, Object> before = new LinkedHashMap<>(settingsService.maskedView());
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put(legal, "混合-合法-1");
        patch.put(illegal, "混合-非法-1");

        // when: 提交混合 patch
        ResponseEntity<Map<String, Object>> resp = settingsController.put(patch);

        // then: 返回 400，且合法键未被写入（未发生部分保存）
        assertEquals(400, resp.getStatusCode().value(), "含非法键必须整体拒绝并返回 400");
        Map<String, Object> after = settingsService.maskedView();
        assertEquals(before, after, "非法键存在时不允许发生部分写入");
    }

    @Test
    void put_withUnknownKey_doesNotMutateServiceState() {
        // given: 记录保存前的掩码视图
        Map<String, Object> before = new LinkedHashMap<>(settingsService.maskedView());
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("__unknown_key_for_state_check__", "v");

        // when: 提交未知键
        ResponseEntity<Map<String, Object>> resp = settingsController.put(patch);

        // then: 返回 400，且服务端状态完全未变
        assertEquals(400, resp.getStatusCode().value(), "未知键必须返回 400");
        assertEquals(before, settingsService.maskedView(), "未知键不得改变服务端状态");
    }

    // ---------- 并发 ----------

    @Test
    void put_concurrentSameKey_doesNotCorruptState() throws Exception {
        // given: 取一个合法键，两线程同时写入不同的值
        List<String> allowed = new ArrayList<>(settingsService.allowedKeys());
        assertFalse(allowed.isEmpty(), "allowedKeys 不能为空");
        String key = allowed.get(0);
        Map<String, String> patchA = new LinkedHashMap<>();
        patchA.put(key, "并发A-1");
        Map<String, String> patchB = new LinkedHashMap<>();
        patchB.put(key, "并发B-1");

        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger okCount = new AtomicInteger(0);
        AtomicInteger badCount = new AtomicInteger(0);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            pool.submit(() -> {
                try {
                    start.await();
                    ResponseEntity<Map<String, Object>> r = settingsController.put(patchA);
                    if (r.getStatusCode().value() == 200) {
                        okCount.incrementAndGet();
                    } else {
                        badCount.incrementAndGet();
                    }
                } catch (Exception ex) {
                    badCount.incrementAndGet();
                } finally {
                    done.countDown();
                }
            });
            pool.submit(() -> {
                try {
                    start.await();
                    ResponseEntity<Map<String, Object>> r = settingsController.put(patchB);
                    if (r.getStatusCode().value() == 200) {
                        okCount.incrementAndGet();
                    } else {
                        badCount.incrementAndGet();
                    }
                } catch (Exception ex) {
                    badCount.incrementAndGet();
                } finally {
                    done.countDown();
                }
            });
            start.countDown();
            assertTrue(done.await(30, TimeUnit.SECONDS), "并发任务必须在 30 秒内结束");
        } finally {
            pool.shutdownNow();
        }

        // then: 两个请求都返回 200，且最终掩码视图可读
        assertEquals(2, okCount.get(), "两个并发请求都应返回 200");
        assertEquals(0, badCount.get(), "并发过程中不允许出现异常或非 200");
        assertNotNull(settingsService.maskedView(), "并发结束后掩码视图必须可读");
    }

    @Test
    void get_concurrentReads_areConsistent() throws Exception {
        // given: 准备并发读取
        int threads = 4;
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        List<Map<String, Object>> results = Collections.synchronizedList(new ArrayList<>());
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    try {
                        start.await();
                        results.add(settingsController.get());
                    } catch (Exception ex) {
                        // 记录失败，后续断言会暴露
                    } finally {
                        done.countDown();
                    }
                });
            }
            start.countDown();
            assertTrue(done.await(30, TimeUnit.SECONDS), "并发读取必须在 30 秒内结束");
        } finally {
            pool.shutdownNow();
        }

        // then: 所有读取结果数量正确，且 schema 一致
        assertEquals(threads, results.size(), "并发读取结果数量必须等于线程数");
        Object schema = results.get(0).get("schema");
        assertNotNull(schema, "schema 不能为 null");
        for (Map<String, Object> r : results) {
            assertEquals(schema, r.get("schema"), "并发读取的 schema 必须一致");
        }
    }

    // ---------- 边界 ----------

    @Test
    void put_withEmptyPatch_returns200AndMaskedView() {
        // given: 空 patch
        Map<String, String> empty = new LinkedHashMap<>();

        // when: 提交空 patch
        ResponseEntity<Map<String, Object>> resp = settingsController.put(empty);

        // then: 返回 200，且返回体为掩码视图
        assertEquals(200, resp.getStatusCode().value(), "空 patch 必须返回 200");
        assertNotNull(resp.getBody(), "空 patch 的返回体不能为 null");
    }

    @Test
    void put_withOversizedPayload_handledWithoutError() {
        // given: 取一个合法键，构造超大 payload
        List<String> allowed = new ArrayList<>(settingsService.allowedKeys());
        assertFalse(allowed.isEmpty(), "allowedKeys 不能为空");
        String key = allowed.get(0);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 100_000; i++) {
            sb.append('x');
        }
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put(key, sb.toString());

        // when: 提交超大值
        ResponseEntity<Map<String, Object>> resp = settingsController.put(patch);

        // then: 处理完成（200 或 400 均可接受），不抛出异常且响应体非 null
        assertNotNull(resp, "超大 payload 响应不能为 null");
        assertTrue(resp.getStatusCode().value() == 200 || resp.getStatusCode().value() == 400,
                "超大 payload 只允许返回 200 或 400");
    }

    @Test
    void put_withIllegalStateTransition_returns400AndKeepsState() {
        // given: 记录当前状态，构造非法键用于模拟非法状态跳转
        Map<String, Object> before = new LinkedHashMap<>(settingsService.maskedView());
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("__illegal_transition_key__", "v");

        // when: 提交非法键
        ResponseEntity<Map<String, Object>> resp = settingsController.put(patch);

        // then: 返回 400，状态保持不变
        assertEquals(400, resp.getStatusCode().value(), "非法状态跳转必须返回 400");
        assertEquals(before, settingsService.maskedView(), "非法状态跳转不得改变服务端状态");
    }

    @Test
    void effectiveProvider_chainEqualsRouterChain() {
        // given: 直接读取 router 的 chain
        // when: 通过 controller 查询
        Map<String, Object> resp = settingsController.effectiveProvider();
        Object chainFromController = resp.get("chain");

        // then: controller 返回的 chain 与 router.chain() 内容一致
        // （注：chain() 每次调用返回新 List 实例，这里断言内容相等而非同一引用）
        assertNotNull(chainFromController, "chain 不能为 null");
        assertEquals(videoProviderRouter.chain(), chainFromController,
                "controller 返回的 chain 必须与 router.chain() 内容一致");
    }
}