package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MediaProvider;
import com.dramafactory.model.ProviderModel;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.repository.ProviderModelRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJpaTest
@Import(ProviderService.class)
class ProviderServiceCoverageTest {

    @Autowired
    private ProviderService providerService;

    @Autowired
    private MediaProviderRepository providerRepository;

    @Autowired
    private ProviderModelRepository modelRepository;

    private MediaProvider saveProvider(String name, String module) {
        MediaProvider p = new MediaProvider();
        p.setName(name);
        p.setModule(module);
        p.setEnabled(Boolean.TRUE);
        p.setCreatedAt(java.time.LocalDateTime.now());
        p.setUpdatedAt(java.time.LocalDateTime.now());
        return providerRepository.save(p);
    }

    private ProviderModel saveModel(MediaProvider provider, String displayName) {
        ProviderModel m = new ProviderModel();
        m.setProvider(provider);
        m.setDisplayName(displayName);
        m.setEnabled(Boolean.TRUE);
        m.setConcurrency(1);
        return modelRepository.save(m);
    }

    // 分支：testConnection/VIDEO名匹配但bean缺失 -> vp==null -> UNSUPPORTED
    @Test
    void testConnectionVideoMatchedButNoBeanUnsupported() {
        MediaProvider p = saveProvider("agnes 4k", "VIDEO");
        ProviderService.TestConnectionResponse r = providerService.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("UNSUPPORTED");
    }

    // 分支：testConnection/IMAGE名匹配但bean缺失 -> ip==null -> UNSUPPORTED
    @Test
    void testConnectionImageMatchedButNoBeanUnsupported() {
        MediaProvider p = saveProvider("dashscope image", "IMAGE");
        ProviderService.TestConnectionResponse r = providerService.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("UNSUPPORTED");
    }

    // 分支：testConnection/MUSIC名不匹配 -> matchMusicProvider 返回 null -> UNSUPPORTED
    @Test
    void testConnectionMusicUnmatchedUnsupported() {
        MediaProvider p = saveProvider("plain tunes", "MUSIC");
        ProviderService.TestConnectionResponse r = providerService.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("UNSUPPORTED");
    }

    // 分支：testConnection/MUSIC名匹配但bean缺失 -> mp==null -> UNSUPPORTED
    @Test
    void testConnectionMusicMatchedButNoBeanUnsupported() {
        MediaProvider p = saveProvider("minimax music", "MUSIC");
        ProviderService.TestConnectionResponse r = providerService.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("UNSUPPORTED");
    }

    // 分支：testConnection/AVATAR名不匹配 -> matchAvatarProvider 返回 null -> UNSUPPORTED
    @Test
    void testConnectionAvatarUnmatchedUnsupported() {
        MediaProvider p = saveProvider("plain avatar", "AVATAR");
        ProviderService.TestConnectionResponse r = providerService.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("UNSUPPORTED");
    }

    // 分支：testConnection/AVATAR名匹配但bean缺失 -> ap==null -> UNSUPPORTED
    @Test
    void testConnectionAvatarMatchedButNoBeanUnsupported() {
        MediaProvider p = saveProvider("d-id 数字人", "AVATAR");
        ProviderService.TestConnectionResponse r = providerService.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("UNSUPPORTED");
    }

    // 分支：testConnection/TEXT模块 -> else 分支 -> UNSUPPORTED 且 detail 含"该模块暂不支持"
    @Test
    void testConnectionTextModuleUnsupported() {
        MediaProvider p = saveProvider("some text svc", "TEXT");
        ProviderService.TestConnectionResponse r = providerService.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("UNSUPPORTED");
        assertThat(r.detail()).contains("该模块暂不支持");
    }

    // 分支：createProvider/name==null -> IllegalArgumentException
    @Test
    void createProviderNullNameThrows() {
        assertThatThrownBy(() -> providerService.createProvider(null, "VIDEO", null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // 分支：createProvider/name 为空白 -> IllegalArgumentException
    @Test
    void createProviderBlankNameThrows() {
        assertThatThrownBy(() -> providerService.createProvider(" ", "VIDEO", null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // 分支：updateProvider/未知 id -> ResourceNotFoundException
    @Test
    void updateProviderUnknownIdThrows() {
        assertThatThrownBy(() -> providerService.updateProvider(
                999999L, "n", "VIDEO", null, null, null, null))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // 分支：updateProvider/name 为空白 -> IllegalArgumentException
    @Test
    void updateProviderBlankNameThrows() {
        ProviderService.ProviderDto created =
                providerService.createProvider("orig name", "VIDEO", null, null, null);
        assertThatThrownBy(() -> providerService.updateProvider(
                created.id(), " ", null, null, null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // 分支：updateProvider/module 为空 -> 保留旧 module 的分支（module!=null && !module.isEmpty() 为 false）
    @Test
    void updateProviderEmptyModuleKeepsOld() {
        ProviderService.ProviderDto created =
                providerService.createProvider("img svc", "IMAGE", null, null, null);
        ProviderService.ProviderDto updated = providerService.updateProvider(
                created.id(), "img svc renamed", "", null, null, null, null);
        assertThat(updated.module()).isEqualTo("IMAGE");
    }

    // 分支：addModel/未知 providerId -> ResourceNotFoundException
    @Test
    void addModelUnknownProviderThrows() {
        assertThatThrownBy(() -> providerService.addModel(
                999999L, "dn", "mid", null, null, null))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // 分支：addModel/displayName 为空白 -> IllegalArgumentException
    @Test
    void addModelBlankDisplayNameThrows() {
        MediaProvider p = saveProvider("svc", "VIDEO");
        assertThatThrownBy(() -> providerService.addModel(
                p.getId(), " ", "mid", null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // 分支：updateModel/未知 providerId -> ResourceNotFoundException
    @Test
    void updateModelUnknownProviderThrows() {
        assertThatThrownBy(() -> providerService.updateModel(
                999999L, 1L, "dn", "mid", null, null, null, null))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // 分支：updateModel/未知 modelId -> ResourceNotFoundException
    @Test
    void updateModelUnknownModelThrows() {
        MediaProvider p = saveProvider("svc", "VIDEO");
        assertThatThrownBy(() -> providerService.updateModel(
                p.getId(), 999999L, "dn", "mid", null, null, null, null))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // 分支：updateModel/provider 与 model 不匹配 -> ResourceNotFoundException
    @Test
    void updateModelProviderMismatchThrows() {
        MediaProvider a = saveProvider("svc A", "VIDEO");
        MediaProvider b = saveProvider("svc B", "VIDEO");
        ProviderModel m = saveModel(a, "model-a");
        assertThatThrownBy(() -> providerService.updateModel(
                b.getId(), m.getId(), "dn", "mid", null, null, null, null))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // 分支：updateModel/displayName 为 null -> IllegalArgumentException
    @Test
    void updateModelBlankDisplayNameThrows() {
        MediaProvider p = saveProvider("svc", "VIDEO");
        ProviderModel m = saveModel(p, "model-x");
        assertThatThrownBy(() -> providerService.updateModel(
                p.getId(), m.getId(), null, "mid", null, null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // 分支：deleteModel/未知 modelId -> ResourceNotFoundException
    @Test
    void deleteModelUnknownModelThrows() {
        MediaProvider p = saveProvider("svc", "VIDEO");
        assertThatThrownBy(() -> providerService.deleteModel(p.getId(), 999999L))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // 分支：deleteModel/provider 与 model 不匹配 -> ResourceNotFoundException
    @Test
    void deleteModelProviderMismatchThrows() {
        MediaProvider a = saveProvider("svc A", "VIDEO");
        MediaProvider b = saveProvider("svc B", "VIDEO");
        ProviderModel m = saveModel(a, "model-a");
        assertThatThrownBy(() -> providerService.deleteModel(b.getId(), m.getId()))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // 分支：deleteProvider/未知 id -> ResourceNotFoundException
    @Test
    void deleteProviderUnknownIdThrows() {
        assertThatThrownBy(() -> providerService.deleteProvider(999999L))
                .isInstanceOf(ResourceNotFoundException.class);
    }
}
