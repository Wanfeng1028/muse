package com.dramafactory.service;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.model.ProviderModel;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.repository.ProviderModelRepository;
import com.dramafactory.service.ProviderService.ModelDto;
import com.dramafactory.service.ProviderService.ProviderDto;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * ProviderService 单元测试：@DataJpaTest + 手动 import service。
 */
@DataJpaTest
@Import(ProviderService.class)
class ProviderServiceTest {

    @Autowired
    private ProviderService providerService;

    @Autowired
    private MediaProviderRepository providerRepository;

    @Autowired
    private ProviderModelRepository modelRepository;

    @Test
    void createProviderWithModels_andList() {
        ProviderDto p = providerService.createProvider(
                "fei855 视频 API", "VIDEO", "示例供应商", "sk-abcdef123456", "https://api.fei855.com");
        assertThat(p.id()).isNotNull();
        assertThat(p.name()).isEqualTo("fei855 视频 API");
        assertThat(p.enabled()).isTrue();

        ModelDto m1 = providerService.addModel(p.id(), "Seedance 2.0（经济版）",
                "seedance_v2.0", "经济版", "便宜档", null);
        ModelDto m2 = providerService.addModel(p.id(), "Seedance 2.0（旗舰版）",
                "seedance_v2.0", "旗舰版", "顶配档", 4);

        assertThat(m1.concurrency()).isEqualTo(1);
        assertThat(m2.concurrency()).isEqualTo(4);

        List<ProviderDto> all = providerService.listProviders();
        assertThat(all).hasSize(1);
        assertThat(all.get(0).models()).hasSize(2);
        assertThat(all.get(0).models().get(0).displayName()).isEqualTo("Seedance 2.0（经济版）");
    }

    @Test
    void maskedKey_format() {
        // 长 key：首 2 + •••• + 末 4
        ProviderDto p1 = providerService.createProvider("a", "VIDEO", null, "ABCDEF1234", null);
        assertThat(p1.maskedKey()).isEqualTo("AB••••1234");

        // 短 key（<6）：全掩码
        ProviderDto p2 = providerService.createProvider("b", "VIDEO", null, "ABC", null);
        assertThat(p2.maskedKey()).isEqualTo("••••");

        // 空 key：空串
        ProviderDto p3 = providerService.createProvider("c", "VIDEO", null, "", null);
        assertThat(p3.maskedKey()).isEmpty();

        // 边界：正好 6 位
        ProviderDto p4 = providerService.createProvider("d", "VIDEO", null, "ABCDEF", null);
        assertThat(p4.maskedKey()).isEqualTo("AB••••CDEF");
    }

    @Test
    void updateProvider_blankApiKey_keepsOriginal() {
        ProviderDto created = providerService.createProvider(
                "p", "VIDEO", null, "sk-ORIGINAL-9999", null);
        Long id = created.id();

        // 空串：保留
        providerService.updateProvider(id, "p2", null, "desc", "", "https://x", Boolean.TRUE);
        MediaProvider after = providerRepository.findById(id).orElseThrow();
        assertThat(after.getApiKey()).isEqualTo("sk-ORIGINAL-9999");

        // null：保留
        providerService.updateProvider(id, "p3", null, "desc", null, "https://x", Boolean.FALSE);
        MediaProvider after2 = providerRepository.findById(id).orElseThrow();
        assertThat(after2.getApiKey()).isEqualTo("sk-ORIGINAL-9999");
        assertThat(after2.getEnabled()).isFalse();

        // 非空：覆盖
        providerService.updateProvider(id, "p4", null, "desc", "sk-NEW-0000", "https://x", null);
        MediaProvider after3 = providerRepository.findById(id).orElseThrow();
        assertThat(after3.getApiKey()).isEqualTo("sk-NEW-0000");
    }

    @Test
    void deleteProvider_cascadesModels() {
        ProviderDto p = providerService.createProvider("p", "VIDEO", null, "sk-123456", null);
        providerService.addModel(p.id(), "m1", "m1", null, null, null);
        providerService.addModel(p.id(), "m2", "m2", null, null, null);

        assertThat(modelRepository.findByProviderIdOrderByIdAsc(p.id())).hasSize(2);

        providerService.deleteProvider(p.id());

        assertThat(providerRepository.findById(p.id())).isEmpty();
        assertThat(modelRepository.findByProviderIdOrderByIdAsc(p.id())).isEmpty();
    }

    @Test
    void module_filterAndFallback() {
        ProviderDto v = providerService.createProvider("v1", "VIDEO", null, "sk-1", null);
        ProviderDto img = providerService.createProvider("i1", "IMAGE", null, "sk-2", null);
        ProviderDto bad = providerService.createProvider("x1", "NOPE", null, "sk-3", null);
        assertThat(v.module()).isEqualTo("VIDEO");
        assertThat(img.module()).isEqualTo("IMAGE");
        assertThat(bad.module()).isEqualTo("VIDEO");

        assertThat(providerService.listProviders("IMAGE")).hasSize(1);
        assertThat(providerService.listProviders("IMAGE").get(0).name()).isEqualTo("i1");
        assertThat(providerService.listProviders("MUSIC")).isEmpty();
        assertThat(providerService.listProviders(null).size()).isGreaterThanOrEqualTo(3);

        providerService.updateProvider(img.id(), "i1", "MUSIC", null, "", null, null);
        assertThat(providerService.listProviders("MUSIC")).hasSize(1);
    }

    @Test
    void addModel_defaultConcurrencyIsOne() {
        ProviderDto p = providerService.createProvider("p", "VIDEO", null, "sk-abcdef", null);
        ModelDto m = providerService.addModel(p.id(), "m", "m", null, null, null);
        assertThat(m.concurrency()).isEqualTo(1);

        ProviderModel stored = modelRepository.findById(m.id()).orElseThrow();
        assertThat(stored.getConcurrency()).isEqualTo(1);
    }
}
