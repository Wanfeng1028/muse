package com.dramafactory;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MediaProvider;
import com.dramafactory.model.ProviderModel;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.repository.ProviderModelRepository;
import com.dramafactory.service.ProviderService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class ProviderServiceDeepTest {

    @Autowired
    private ProviderService providerService;

    @Autowired
    private MediaProviderRepository providerRepository;

    @Autowired
    private ProviderModelRepository modelRepository;

    @BeforeEach
    void cleanUp() {
        modelRepository.deleteAll();
        providerRepository.deleteAll();
    }

    private MediaProvider newProvider(String name, String module, String apiKey) {
        MediaProvider p = new MediaProvider();
        p.setName(name);
        p.setModule(module);
        p.setDescription(name + " desc");
        p.setApiKey(apiKey);
        p.setApiAddress("https://api." + name + ".example.com");
        p.setEnabled(Boolean.TRUE);
        p.setCreatedAt(java.time.LocalDateTime.now());
        p.setUpdatedAt(java.time.LocalDateTime.now());
        return providerRepository.save(p);
    }

    private ProviderModel newModel(MediaProvider p, String displayName, String modelId, Integer concurrency, Boolean enabled) {
        ProviderModel m = new ProviderModel();
        m.setProvider(p);
        m.setDisplayName(displayName);
        m.setModelId(modelId);
        m.setScale("standard");
        m.setDescription(displayName + " desc");
        m.setConcurrency(concurrency);
        m.setEnabled(enabled);
        return modelRepository.save(m);
    }

    @Test
    void createProvider_persistsAndReturnsDto_withMaskedKey() {
        // given: 一个还没有任何供应商的空库
        assertEquals(0L, providerRepository.count());

        // when: 调用 createProvider 写入一条视频供应商
        ProviderService.ProviderDto dto = providerService.createProvider(
                "deepseek", "VIDEO", "视频供应商", "sk-abcdefghijklmnop", "https://api.deepseek.example.com");

        // then: 返回 DTO 字段正确、库里有且只有一条记录、密钥原文不出现在 DTO 中
        assertNotNull(dto.id());
        assertEquals("deepseek", dto.name());
        assertEquals("VIDEO", dto.module());
        assertEquals("https://api.deepseek.example.com", dto.apiAddress());
        assertEquals(Boolean.TRUE, dto.enabled());
        assertEquals(1L, providerRepository.count());
        assertNotEquals("sk-abcdefghijklmnop", dto.maskedKey());
        assertFalse(dto.maskedKey() == null || dto.maskedKey().isEmpty());
    }

    @Test
    void createProvider_blankName_throwsIllegalArgument_andDoesNotPersist() {
        // given: 一个还没有任何供应商的空库
        assertEquals(0L, providerRepository.count());

        // when: 用空白 name 调 createProvider
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> providerService.createProvider("   ", "VIDEO", "desc", "sk-1", "https://x.example.com"));

        // then: 异常信息符合预期、库里没有新增记录
        assertEquals("name must not be blank", ex.getMessage());
        assertEquals(0L, providerRepository.count());
    }

    @Test
    void listProviders_withModuleFilter_returnsOnlyThatModule() {
        // given: 库里有 VIDEO 和 MUSIC 各一条
        newProvider("alpha", "VIDEO", "sk-a");
        newProvider("beta", "MUSIC", "sk-b");

        // when: 按 VIDEO 过滤查询
        List<ProviderService.ProviderDto> videoList = providerService.listProviders("VIDEO");

        // then: 只返回 VIDEO 那条，查全部则返回两条
        assertEquals(1, videoList.size());
        assertEquals("alpha", videoList.get(0).name());
        assertEquals("VIDEO", videoList.get(0).module());
        List<ProviderService.ProviderDto> all = providerService.listProviders();
        assertEquals(2, all.size());
    }

    @Test
    void listProviders_nullModule_returnsAllInIdOrder() {
        // given: 库里有两条不同模块的供应商
        MediaProvider first = newProvider("first", "VIDEO", "sk-1");
        MediaProvider second = newProvider("second", "IMAGE", "sk-2");

        // when: 传 null 模块查询
        List<ProviderService.ProviderDto> result = providerService.listProviders(null);

        // then: 返回全部、按 id 升序、第一条是 first
        assertEquals(2, result.size());
        assertEquals(first.getId(), result.get(0).id());
        assertEquals(second.getId(), result.get(1).id());
    }

    @Test
    void updateProvider_emptyApiKey_keepsOriginalKey() {
        // given: 已存在一条带原始密钥的供应商
        MediaProvider p = newProvider("keep", "VIDEO", "sk-original-secret");
        Long id = p.getId();
        String originalKey = providerRepository.findById(id).orElseThrow().getApiKey();
        assertEquals("sk-original-secret", originalKey);

        // when: 用空 apiKey 调 updateProvider
        ProviderService.ProviderDto dto = providerService.updateProvider(
                id, "keep", "VIDEO", "新描述", "", "https://new.example.com", Boolean.FALSE);

        // then: 密钥保持原值、其他字段被更新
        MediaProvider reloaded = providerRepository.findById(id).orElseThrow();
        assertEquals("sk-original-secret", reloaded.getApiKey());
        assertEquals("新描述", reloaded.getDescription());
        assertEquals("https://new.example.com", reloaded.getApiAddress());
        assertEquals(Boolean.FALSE, reloaded.getEnabled());
        assertEquals("新描述", dto.description());
    }

    @Test
    void updateProvider_nonExistingId_throwsResourceNotFound() {
        // given: 一个不存在的 id
        long missingId = 987654321L;
        assertEquals(0L, providerRepository.count());

        // when: 用这个 id 调 updateProvider
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> providerService.updateProvider(missingId, "x", "VIDEO", "d", "k", "a", Boolean.TRUE));

        // then: 异常携带正确的资源名和 id、库里依旧为空
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains("provider"));
        assertEquals(0L, providerRepository.count());
    }

    @Test
    void addModel_persistsAndDefaultsConcurrencyToOne() {
        // given: 已存在一条供应商
        MediaProvider p = newProvider("host", "VIDEO", "sk-host");

        // when: 传 concurrency 为 null 调 addModel
        ProviderService.ModelDto dto = providerService.addModel(
                p.getId(), "gpt-video", "gpt-video-1", "standard", "默认并发模型", null);

        // then: 返回 DTO 有 id、并发默认成 1、库里存在该模型
        assertNotNull(dto.id());
        assertEquals("gpt-video", dto.displayName());
        assertEquals(1, dto.concurrency());
        assertEquals(Boolean.TRUE, dto.enabled());
        assertTrue(modelRepository.findById(dto.id()).isPresent());
    }

    @Test
    void addModel_blankDisplayName_throwsIllegalArgument_andDoesNotPersist() {
        // given: 已存在一条供应商，模型表为空
        MediaProvider p = newProvider("host2", "VIDEO", "sk-host2");
        assertEquals(0L, modelRepository.count());

        // when: 用空白 displayName 调 addModel
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> providerService.addModel(p.getId(), "   ", "m-1", "standard", "d", 2));

        // then: 异常信息正确、模型表仍为空
        assertEquals("displayName must not be blank", ex.getMessage());
        assertEquals(0L, modelRepository.count());
    }

    @Test
    void updateModel_providerMismatch_throwsResourceNotFound() {
        // given: 两个供应商，各自挂一个模型
        MediaProvider a = newProvider("a", "VIDEO", "sk-a");
        MediaProvider b = newProvider("b", "VIDEO", "sk-b");
        ProviderModel modelOfA = newModel(a, "model-a", "ma", 1, Boolean.TRUE);
        Long modelId = modelOfA.getId();

        // when: 用供应商 b 的 id 去更新属于 a 的模型
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> providerService.updateModel(b.getId(), modelId, "renamed", "ma", "s", "d", 2, Boolean.TRUE));

        // then: 抛出 model 未找到、模型显示名没被改
        assertTrue(ex.getMessage().contains("model"));
        assertEquals("model-a", modelRepository.findById(modelId).orElseThrow().getDisplayName());
    }

    @Test
    void deleteProvider_cascadesModels_andRemovesBoth() {
        // given: 一条供应商挂两个模型
        MediaProvider p = newProvider("todelete", "VIDEO", "sk-del");
        Long pid = p.getId();
        ProviderModel m1 = newModel(p, "m1", "m1", 1, Boolean.TRUE);
        ProviderModel m2 = newModel(p, "m2", "m2", 2, Boolean.TRUE);
        Long m1Id = m1.getId();
        Long m2Id = m2.getId();
        assertEquals(1L, providerRepository.count());
        assertEquals(2L, modelRepository.count());

        // when: 删除该供应商
        providerService.deleteProvider(pid);

        // then: 供应商和它的模型全没了，其他不存在
        assertFalse(providerRepository.findById(pid).isPresent());
        assertFalse(modelRepository.findById(m1Id).isPresent());
        assertFalse(modelRepository.findById(m2Id).isPresent());
        assertEquals(0L, modelRepository.count());
    }

    @Test
    void deleteModel_wrongProvider_throwsResourceNotFound_andKeepsModel() {
        // given: 供应商 x 带一个模型，供应商 y 与它无关
        MediaProvider x = newProvider("x", "VIDEO", "sk-x");
        MediaProvider y = newProvider("y", "VIDEO", "sk-y");
        ProviderModel model = newModel(x, "mx", "mx", 1, Boolean.TRUE);
        Long modelId = model.getId();

        // when: 用供应商 y 的 id 去删 x 的模型
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> providerService.deleteModel(y.getId(), modelId));

        // then: 异常信息含 model、模型仍然存在
        assertTrue(ex.getMessage().contains("model"));
        assertTrue(modelRepository.findById(modelId).isPresent());
    }

    @Test
    void listProviders_masksKey_neverLeaksPlainKey() {
        // given: 一条带明文密钥的供应商
        String plain = "sk-plain-very-secret-1234567890";
        newProvider("leakcheck", "VIDEO", plain);

        // when: 查询列表
        List<ProviderService.ProviderDto> result = providerService.listProviders();

        // then: 返回非空、掩码不等于明文、且掩码里不含明文片段
        assertEquals(1, result.size());
        String masked = result.get(0).maskedKey();
        assertNotNull(masked);
        assertNotEquals(plain, masked);
        assertFalse(masked.contains(plain));
    }

    @Test
    void createProvider_normalizesModule_uppercase() {
        // given: 空库
        assertEquals(0L, providerRepository.count());

        // when: 用一个小写模块名创建
        ProviderService.ProviderDto dto = providerService.createProvider(
                "norm", "video", "desc", "sk-norm", "https://n.example.com");

        // then: 模块被规整成大写 VIDEO、库里存的值也是大写
        assertEquals("VIDEO", dto.module());
        MediaProvider stored = providerRepository.findById(dto.id()).orElseThrow();
        assertEquals("VIDEO", stored.getModule());
    }

    @Test
    void updateModel_partialFields_keepsProviderLink() {
        // given: 一条供应商带一个模型
        MediaProvider p = newProvider("partial", "VIDEO", "sk-partial");
        ProviderModel m = newModel(p, "orig", "orig-m", 3, Boolean.TRUE);
        Long modelId = m.getId();

        // when: 更新模型名和并发，不动 provider
        ProviderService.ModelDto dto = providerService.updateModel(
                p.getId(), modelId, "renamed", "new-m", "large", "d2", 8, Boolean.FALSE);

        // then: 返回 DTO 反映新值、库里的 provider 关联没变
        assertEquals("renamed", dto.displayName());
        assertEquals(8, dto.concurrency());
        assertEquals(Boolean.FALSE, dto.enabled());
        ProviderModel reloaded = modelRepository.findById(modelId).orElseThrow();
        assertEquals(p.getId(), reloaded.getProvider().getId());
        assertEquals("new-m", reloaded.getModelId());
    }

    @Test
    void addModel_nonExistingProvider_throwsResourceNotFound() {
        // given: 一个不存在的 provider id
        long missingId = 555555555L;
        assertEquals(0L, providerRepository.count());

        // when: 往这个 id 下加模型
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> providerService.addModel(missingId, "m", "m-1", "standard", "d", 1));

        // then: 异常含 provider、模型表仍为空
        assertTrue(ex.getMessage().contains("provider"));
        assertEquals(0L, modelRepository.count());
    }

    @Test
    void deleteProvider_nonExistingId_throwsResourceNotFound() {
        // given: 一个不存在的 id
        long missingId = 424242424L;

        // when: 删除这个 id
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> providerService.deleteProvider(missingId));

        // then: 异常含 provider、库里没变化
        assertTrue(ex.getMessage().contains("provider"));
        assertEquals(0L, providerRepository.count());
    }
}