package com.dramafactory.service;

import com.dramafactory.service.SettingsService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import java.io.IOException;
import java.lang.reflect.Constructor;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class SettingsServiceDeepTest {

    @Autowired
    private ApplicationContext applicationContext;

    private Path tempDir;

    private Path settingsFile;

    private SettingsService service;

    @BeforeEach
    void setUp() throws IOException {
        tempDir = Files.createTempDirectory("settings-deep-test-");
        settingsFile = tempDir.resolve("settings.json");
        service = newServiceWithPath(settingsFile);
    }

    /**
     * 通过反射调用包级可见的 {@code SettingsService(Path)} 测试构造器，
     * 避免本测试类（位于 com.dramafactory 包）无法直接访问 service 包级构造器。
     */
    private static SettingsService newServiceWithPath(Path path) {
        try {
            Constructor<SettingsService> ctor = SettingsService.class.getDeclaredConstructor(Path.class);
            ctor.setAccessible(true);
            return ctor.newInstance(path);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("无法构造隔离路径的 SettingsService", e);
        }
    }

    @Test
    @DisplayName("Spring 上下文能拿到 SettingsService bean，且默认构造器路径为 data/settings.json")
    void springContextProvidesSettingsServiceBean() {
        // given: 真实启动的 Spring 上下文
        // when: 从容器按类型取 SettingsService
        SettingsService bean = applicationContext.getBean(SettingsService.class);
        // then: bean 存在，且默认路径常量与默认构造器路径一致
        assertNotNull(bean);
        assertEquals("data/settings.json", SettingsService.SETTINGS_PATH);
        assertTrue(SettingsService.SECRET_KEYS.contains("deepseek.api-key"));
    }

    @Test
    @DisplayName("文件不存在时 loadAll 返回空 Map，写入后能读回同样内容")
    void loadAllReturnsEmptyWhenFileMissingThenRoundTrips() {
        // given: 文件尚未创建
        assertFalse(Files.isRegularFile(settingsFile));
        // when: 读取空文件
        Map<String, String> empty = service.loadAll();
        // then: 返回空 Map，且不是 null
        assertNotNull(empty);
        assertTrue(empty.isEmpty());

        // given: 准备一份普通键值
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("deepseek.base-url", "https://api.deepseek.com");
        patch.put("drama.storage", "./data/media");
        // when: 保存后再读取
        service.saveAll(patch);
        Map<String, String> reloaded = service.loadAll();
        // then: 内容一致，文件真实存在
        assertEquals(2, reloaded.size());
        assertEquals("https://api.deepseek.com", reloaded.get("deepseek.base-url"));
        assertEquals("./data/media", reloaded.get("drama.storage"));
        assertTrue(Files.isRegularFile(settingsFile));
    }

    @Test
    @DisplayName("secret 键空串保持原值，非 secret 键空串删除键")
    void secretBlankKeepsValueNonSecretBlankRemovesKey() {
        // given: 先写入一个 secret 和一个普通键
        Map<String, String> init = new LinkedHashMap<>();
        init.put("deepseek.api-key", "sk-real-value-1234");
        init.put("deepseek.model", "deepseek-chat");
        service.saveAll(init);

        // when: 对 secret 传空串、对普通键传空串
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("deepseek.api-key", "");
        patch.put("deepseek.model", "");
        service.saveAll(patch);

        // then: secret 保留原值，普通键被删除
        Map<String, String> after = service.loadAll();
        assertEquals("sk-real-value-1234", after.get("deepseek.api-key"));
        assertFalse(after.containsKey("deepseek.model"));
    }

    @Test
    @DisplayName("mask 保留后 4 位，短值一律打 ****，空值返回空串")
    void maskKeepsTailFourAndHandlesShortAndEmpty() {
        // given: 不同长度的密钥
        String longValue = "sk-abcdefghijklmnop";
        String shortValue = "abc";
        String fourValue = "abcd";
        // when: 逐个掩码
        String maskedLong = SettingsService.mask(longValue);
        String maskedShort = SettingsService.mask(shortValue);
        String maskedFour = SettingsService.mask(fourValue);
        String maskedEmpty = SettingsService.mask("");
        String maskedNull = SettingsService.mask(null);
        // then: 长值保留后 4 位，短值 ****，空/null 为空串
        assertEquals("****mnop", maskedLong);
        assertEquals("****", maskedShort);
        assertEquals("****", maskedFour);
        assertEquals("", maskedEmpty);
        assertEquals("", maskedNull);
    }

    @Test
    @DisplayName("maskedView 对 secret 掩码，对普通键原样返回")
    void maskedViewMasksSecretsAndKeepsPlainValues() {
        // given: 写入 secret 与普通键
        Map<String, String> init = new LinkedHashMap<>();
        init.put("deepseek.api-key", "sk-1234567890abcd");
        init.put("harness.ui.theme", "dark");
        service.saveAll(init);

        // when: 取掩码视图
        Map<String, Object> view = service.maskedView();

        // then: secret 已掩码，普通键原样
        assertEquals("****abcd", view.get("deepseek.api-key"));
        assertEquals("dark", view.get("harness.ui.theme"));
        assertFalse(String.valueOf(view.get("deepseek.api-key")).contains("1234567890"));
    }

    @Test
    @DisplayName("schema 包含 12 个字段，allowedKeys 与 schema 键集合完全一致")
    void schemaAndAllowedKeysAreConsistent() {
        // given: 直接调用 schema()
        // when: 取 schema 与 allowedKeys
        List<Map<String, Object>> schema = service.schema();
        Set<String> allowed = service.allowedKeys();

        // then: 数量、键集合、每个字段都带 key/label/type
        assertEquals(12, schema.size());
        assertEquals(12, allowed.size());
        for (Map<String, Object> field : schema) {
            assertNotNull(field.get("key"));
            assertNotNull(field.get("label"));
            assertNotNull(field.get("type"));
            assertTrue(allowed.contains(String.valueOf(field.get("key"))));
        }
        assertTrue(allowed.contains("drama.video.provider"));
        assertTrue(allowed.contains("harness.qc.manual-approval"));
    }

    @Test
    @DisplayName("select 字段 options 完整，password 字段 secret 为 true")
    void schemaSelectOptionsAndSecretFlagsAreCorrect() {
        // given: 遍历 schema 找到视频通道与密钥字段
        Map<String, Map<String, Object>> byKey = new LinkedHashMap<>();
        for (Map<String, Object> f : service.schema()) {
            byKey.put(String.valueOf(f.get("key")), f);
        }

        // when: 取字段定义
        Map<String, Object> provider = byKey.get("drama.video.provider");
        Map<String, Object> theme = byKey.get("harness.ui.theme");
        Map<String, Object> apiKey = byKey.get("deepseek.api-key");

        // then: options 与 secret 标记符合预期
        assertEquals(List.of("mock", "qwen", "agnes"), provider.get("options"));
        assertEquals(List.of("light", "dark"), theme.get("options"));
        assertEquals(Boolean.TRUE, apiKey.get("secret"));
        assertEquals("password", apiKey.get("type"));
        assertFalse((Boolean) provider.get("secret"));
    }

    @Test
    @DisplayName("重复调用 saveAll 同一 patch 结果幂等，文件内容不变")
    void repeatedSaveAllIsIdempotent() throws IOException {
        // given: 一份 patch
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("drama.video.max-attempts", "3");
        patch.put("drama.video.poll-interval-ms", "5000");

        // when: 连续保存三次
        service.saveAll(patch);
        byte[] first = Files.readAllBytes(settingsFile);
        service.saveAll(patch);
        byte[] second = Files.readAllBytes(settingsFile);
        service.saveAll(patch);
        byte[] third = Files.readAllBytes(settingsFile);

        // then: 三次字节完全一致，读回值也一致
        assertTrue(java.util.Arrays.equals(first, second));
        assertTrue(java.util.Arrays.equals(second, third));
        Map<String, String> reloaded = service.loadAll();
        assertEquals("3", reloaded.get("drama.video.max-attempts"));
        assertEquals("5000", reloaded.get("drama.video.poll-interval-ms"));
    }

    @Test
    @DisplayName("loadAll 在文件内容为空字节时返回空 Map，不抛异常")
    void loadAllReturnsEmptyOnZeroByteFile() throws IOException {
        // given: 先建目录并写入 0 字节文件
        Files.createDirectories(settingsFile.getParent());
        Files.write(settingsFile, new byte[0]);
        assertTrue(Files.isRegularFile(settingsFile));
        assertEquals(0L, Files.size(settingsFile));

        // when: 读取
        Map<String, String> result = service.loadAll();

        // then: 返回空 Map，没有抛异常
        assertNotNull(result);
        assertTrue(result.isEmpty());
    }

    @Test
    @DisplayName("写入超长 value（1MB）后能完整读回，长度与内容一致")
    void largePayloadRoundTripsWithoutTruncation() {
        // given: 构造 1MB 的 value
        int size = 1024 * 1024;
        StringBuilder sb = new StringBuilder(size);
        for (int i = 0; i < size; i++) {
            sb.append((char) ('a' + (i % 26)));
        }
        String big = sb.toString();
        assertEquals(size, big.length());

        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("drama.storage", big);

        // when: 保存后读回
        service.saveAll(patch);
        Map<String, String> reloaded = service.loadAll();
        String readBack = reloaded.get("drama.storage");

        // then: 长度一致，首尾字符一致
        assertNotNull(readBack);
        assertEquals(size, readBack.length());
        assertEquals(big.charAt(0), readBack.charAt(0));
        assertEquals(big.charAt(size - 1), readBack.charAt(size - 1));
    }

    @Test
    @DisplayName("patch 中的非法 key（null/空白）被忽略，合法 key 正常写入")
    void blankAndNullKeysAreIgnored() {
        // given: 一个包含非法 key 的 patch
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("", "ignored");
        patch.put("   ", "ignored-too");
        patch.put(null, "ignored-null");
        patch.put("deepseek.model", "deepseek-chat");

        // when: 保存
        service.saveAll(patch);
        Map<String, String> reloaded = service.loadAll();

        // then: 只有合法键落地
        assertEquals(1, reloaded.size());
        assertEquals("deepseek-chat", reloaded.get("deepseek.model"));
        assertFalse(reloaded.containsKey(""));
    }

    @Test
    @DisplayName("patch 为 null 时不报错，且不清空已有设置")
    void nullPatchDoesNotThrowAndKeepsExisting() {
        // given: 先写入一个设置
        Map<String, String> init = new LinkedHashMap<>();
        init.put("harness.ui.language", "zh");
        service.saveAll(init);

        // when: 传入 null patch
        service.saveAll(null);

        // then: 不抛异常，原值仍在
        Map<String, String> reloaded = service.loadAll();
        assertEquals("zh", reloaded.get("harness.ui.language"));
        assertEquals(1, reloaded.size());
    }

    @Test
    @DisplayName("并发写入同一 key 时数据不坏，最终值为某一次写入的完整值")
    void concurrentSaveAllOnSameKeyDoesNotCorruptData() throws Exception {
        // given: 两个线程各自写不同的完整值到同一个 key
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger errors = new AtomicInteger();
        String valueA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        String valueB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

        // when: 同时启动两个写入线程
        pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < 30; i++) {
                    Map<String, String> patch = new LinkedHashMap<>();
                    patch.put("deepseek.base-url", valueA);
                    service.saveAll(patch);
                }
            } catch (Exception e) {
                errors.incrementAndGet();
            } finally {
                done.countDown();
            }
        });
        pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < 30; i++) {
                    Map<String, String> patch = new LinkedHashMap<>();
                    patch.put("deepseek.base-url", valueB);
                    service.saveAll(patch);
                }
            } catch (Exception e) {
                errors.incrementAndGet();
            } finally {
                done.countDown();
            }
        });
        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then: 无异常，最终值必为 A 或 B 之一，文件可被重新解析
        assertTrue(finished);
        assertEquals(0, errors.get());
        Map<String, String> reloaded = service.loadAll();
        String finalValue = reloaded.get("deepseek.base-url");
        assertNotNull(finalValue);
        assertTrue(valueA.equals(finalValue) || valueB.equals(finalValue));
        assertEquals(40, finalValue.length());
    }

    @Test
    @DisplayName("并发读写交错时读到的每个值都是完整值，不会读到半截 JSON")
    void concurrentReadWriteNeverYieldsPartialJson() throws Exception {
        // given: 一个写线程反复写，一个读线程反复读
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch firstWrite = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger errors = new AtomicInteger();
        List<String> observed = new ArrayList<>();
        String[] values = {
                "v-11111111111111111111111111111111",
                "v-22222222222222222222222222222222",
                "v-33333333333333333333333333333333"
        };

        // when: 写入线程和读取线程同时跑
        pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < 60; i++) {
                    Map<String, String> patch = new LinkedHashMap<>();
                    patch.put("drama.video.max-attempts", values[i % values.length]);
                    service.saveAll(patch);
                    if (i == 0) {
                        firstWrite.countDown();
                    }
                }
            } catch (Exception e) {
                errors.incrementAndGet();
            } finally {
                done.countDown();
            }
        });
        pool.submit(() -> {
            try {
                start.await();
                firstWrite.await(10, TimeUnit.SECONDS);
                for (int i = 0; i < 60; i++) {
                    Map<String, String> read = service.loadAll();
                    String v = read.get("drama.video.max-attempts");
                    if (v != null) {
                        synchronized (observed) {
                            observed.add(v);
                        }
                    }
                }
            } catch (Exception e) {
                errors.incrementAndGet();
            } finally {
                done.countDown();
            }
        });
        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then: 无异常，所有观测值都属于三个完整值之一
        assertTrue(finished);
        assertEquals(0, errors.get());
        assertFalse(observed.isEmpty());
        List<String> allowed = List.of(values);
        synchronized (observed) {
            for (String v : observed) {
                assertTrue(allowed.contains(v), "观测到非完整值: " + v);
            }
        }
    }

    @Test
    @DisplayName("loadAll 在文件内容为非法 JSON 时抛出 IllegalStateException")
    void loadAllThrowsOnMalformedJson() throws IOException {
        // given: 写入一段非法 JSON
        Files.createDirectories(settingsFile.getParent());
        Files.write(settingsFile, "{ this is not valid json".getBytes(java.nio.charset.StandardCharsets.UTF_8));

        // when / then: 读取时抛 IllegalStateException，且信息包含设置路径
        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> service.loadAll());
        assertTrue(ex.getMessage().contains(SettingsService.SETTINGS_PATH));
    }
}