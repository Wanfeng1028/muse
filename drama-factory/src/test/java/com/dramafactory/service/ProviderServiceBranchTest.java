package com.dramafactory.service;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.model.ProviderModel;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.repository.ProviderModelRepository;
import com.dramafactory.service.byok.AvatarProvider;
import com.dramafactory.service.byok.ImageProvider;
import com.dramafactory.service.byok.MusicProvider;
import com.dramafactory.service.video.VideoProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import java.lang.reflect.Method;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

@DataJpaTest
@Import(ProviderService.class)
class ProviderServiceBranchTest {

    @Autowired
    ProviderService providerService;

    @Autowired
    MediaProviderRepository providerRepository;

    @Autowired
    ProviderModelRepository modelRepository;

    private MediaProvider saveProvider(String name, String module) {
        MediaProvider p = new MediaProvider();
        p.setName(name);
        p.setModule(module);
        p.setEnabled(Boolean.TRUE);
        LocalDateTime now = LocalDateTime.now();
        p.setCreatedAt(now);
        p.setUpdatedAt(now);
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

    @Test
    // 覆盖 L53/60/67：构造器 if (imageProviders != null) / if (musicProviders != null) / if (avatarProviders != null) 的 null 分支
    void testConstructorNullMapsDoNotThrowAndListStillWorks() {
        saveProvider("p1", "VIDEO");
        ProviderService svc = new ProviderService(providerRepository, modelRepository,
                null, null, null, null);
        List<ProviderService.ProviderDto> all = svc.listProviders();
        assertThat(all).hasSize(1);
        assertThat(all.get(0).name()).isEqualTo("p1");
    }

    @Test
    // 覆盖 L115：listProviders(module) 的 module == null || module.isEmpty() 真分支与假分支
    void testListProvidersEmptyModuleReturnsAllThenFilters() {
        saveProvider("a", "VIDEO");
        saveProvider("b", "IMAGE");
        List<ProviderService.ProviderDto> all = providerService.listProviders("");
        assertThat(all).hasSize(2);
        List<ProviderService.ProviderDto> videos = providerService.listProviders("VIDEO");
        assertThat(videos).hasSize(1);
        assertThat(videos.get(0).name()).isEqualTo("a");
    }

    @Test
    // 覆盖 L157：updateProvider name 校验 null 分支
    void testUpdateProviderNullNameThrows() {
        MediaProvider p = saveProvider("orig", "VIDEO");
        assertThatThrownBy(() -> providerService.updateProvider(p.getId(), null, null, null, null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    // 覆盖 L157 假分支 + L161 module == null || module.isEmpty() 真分支（module 保持原值）
    void testUpdateProviderNullModuleKeepsOriginal() {
        MediaProvider p = saveProvider("orig", "VIDEO");
        ProviderService.ProviderDto dto = providerService.updateProvider(
                p.getId(), "新名字", null, null, null, null, null);
        assertThat(dto.name()).isEqualTo("新名字");
        assertThat(dto.module()).isEqualTo("VIDEO");
    }

    @Test
    // 覆盖 L199：addModel displayName 校验 null 分支
    void testAddModelNullDisplayNameThrows() {
        MediaProvider p = saveProvider("p", "VIDEO");
        assertThatThrownBy(() -> providerService.addModel(p.getId(), null, "m", null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    // 覆盖 L228：updateModel displayName 校验 null 分支
    void testUpdateModelNullDisplayNameThrows() {
        MediaProvider p = saveProvider("p", "VIDEO");
        ProviderModel m = saveModel(p, "orig");
        assertThatThrownBy(() -> providerService.updateModel(
                p.getId(), m.getId(), null, "mid", null, null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    // 覆盖 L228 假分支：displayName 有效时成功更新
    void testUpdateModelValidDisplayNameUpdates() {
        MediaProvider p = saveProvider("p", "VIDEO");
        ProviderModel m = saveModel(p, "orig");
        ProviderService.ModelDto dto = providerService.updateModel(
                p.getId(), m.getId(), "有效名", "mid", null, null, null, null);
        assertThat(dto.displayName()).isEqualTo("有效名");
        assertThat(dto.modelId()).isEqualTo("mid");
    }

    @Test
    // 覆盖 L235：updateModel if (concurrency != null) 真分支
    void testUpdateModelConcurrencyNonNullUpdates() {
        MediaProvider p = saveProvider("p", "VIDEO");
        ProviderModel m = saveModel(p, "orig");
        ProviderService.ModelDto dto = providerService.updateModel(
                p.getId(), m.getId(), "有效名", null, null, null, 5, null);
        assertThat(dto.concurrency()).isEqualTo(5);
    }

    @Test
    // 覆盖 L235：updateModel if (concurrency != null) 假分支（保留原值）
    void testUpdateModelConcurrencyNullKeepsOriginal() {
        MediaProvider p = saveProvider("p", "VIDEO");
        ProviderModel m = saveModel(p, "orig");
        providerService.updateModel(p.getId(), m.getId(), "有效名", null, null, null, 5, null);
        ProviderService.ModelDto dto = providerService.updateModel(
                p.getId(), m.getId(), "有效名", null, null, null, null, null);
        assertThat(dto.concurrency()).isEqualTo(5);
    }

    @Test
    // 覆盖 L238：updateModel if (enabled != null) 真分支
    void testUpdateModelEnabledNonNullUpdates() {
        MediaProvider p = saveProvider("p", "VIDEO");
        ProviderModel m = saveModel(p, "orig");
        ProviderService.ModelDto dto = providerService.updateModel(
                p.getId(), m.getId(), "有效名", null, null, null, null, false);
        assertThat(dto.enabled()).isFalse();
    }

    @Test
    // 覆盖 L238：updateModel if (enabled != null) 假分支（保留原值）
    void testUpdateModelEnabledNullKeepsOriginal() {
        MediaProvider p = saveProvider("p", "VIDEO");
        ProviderModel m = saveModel(p, "orig");
        providerService.updateModel(p.getId(), m.getId(), "有效名", null, null, null, null, false);
        ProviderService.ModelDto dto = providerService.updateModel(
                p.getId(), m.getId(), "有效名", null, null, null, null, null);
        assertThat(dto.enabled()).isFalse();
    }

    @Test
    // 覆盖 L251：deleteModel 校验通过后的成功删除路径
    void testDeleteModelSuccessPathRemovesModel() {
        MediaProvider p = saveProvider("p", "VIDEO");
        ProviderModel m = saveModel(p, "orig");
        providerService.deleteModel(p.getId(), m.getId());
        assertThat(modelRepository.findById(m.getId())).isEmpty();
    }

    @Test
    // 覆盖 L290：testConnection IMAGE 且 bean 命中分支
    void testConnectionImageMatchedBeanReturnsOk() {
        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.name()).thenReturn("dashscope-image");
        when(imageProvider.probe(any(), any()))
                .thenReturn(new ImageProvider.ConnectivityResult(
                        VideoProvider.ConnectivityStatus.OK, "ok"));
        ProviderService svc = new ProviderService(providerRepository, modelRepository,
                Map.of(), Map.of("dashscope-image", imageProvider), Map.of(), Map.of());
        MediaProvider p = saveProvider("dashscope image", "IMAGE");
        ProviderService.TestConnectionResponse r = svc.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("OK");
        assertThat(r.detail()).isEqualTo("ok");
    }

    @Test
    // 覆盖 L299：testConnection MUSIC 且 bean 命中分支
    void testConnectionMusicMatchedBeanReturnsOk() {
        MusicProvider musicProvider = mock(MusicProvider.class);
        when(musicProvider.name()).thenReturn("minimax-music");
        when(musicProvider.probe(any(), any()))
                .thenReturn(new MusicProvider.ConnectivityResult(
                        VideoProvider.ConnectivityStatus.OK, "ok"));
        ProviderService svc = new ProviderService(providerRepository, modelRepository,
                Map.of(), Map.of(), Map.of("minimax-music", musicProvider), Map.of());
        MediaProvider p = saveProvider("minimax music", "MUSIC");
        ProviderService.TestConnectionResponse r = svc.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("OK");
        assertThat(r.detail()).isEqualTo("ok");
    }

    @Test
    // 覆盖 L308：testConnection AVATAR 且 bean 命中分支
    void testConnectionAvatarMatchedBeanReturnsOk() {
        AvatarProvider avatarProvider = mock(AvatarProvider.class);
        when(avatarProvider.name()).thenReturn("did-avatar");
        when(avatarProvider.probe(any()))
                .thenReturn(new AvatarProvider.ConnectivityResult(
                        VideoProvider.ConnectivityStatus.OK, "ok"));
        ProviderService svc = new ProviderService(providerRepository, modelRepository,
                Map.of(), Map.of(), Map.of(), Map.of("did-avatar", avatarProvider));
        MediaProvider p = saveProvider("d-id avatar", "AVATAR");
        ProviderService.TestConnectionResponse r = svc.testConnection(p.getId());
        assertThat(r.status()).isEqualTo("OK");
        assertThat(r.detail()).isEqualTo("ok");
    }

    @Test
    // 覆盖 L333/L334：matchVideoProvider 的 qwen/dashscope || 链（切片无 bean → UNSUPPORTED）
    void testConnectionVideoQwenDashscopeUnsupported() {
        MediaProvider qwen = saveProvider("qwen-max", "VIDEO");
        MediaProvider dashscope = saveProvider("mock video", "VIDEO");
        ProviderService.TestConnectionResponse r1 = providerService.testConnection(qwen.getId());
        ProviderService.TestConnectionResponse r2 = providerService.testConnection(dashscope.getId());
        assertThat(r1.status()).isEqualTo("UNSUPPORTED");
        assertThat(r2.status()).isEqualTo("UNSUPPORTED");
    }
    // 覆盖 L344：matchImageProvider name==null 防御分支（DB 有 NOT NULL 约束，public 路径不可达，改反射直测）
    @Test
    void testConnectionImageNullNameUnsupported() throws Exception {
    ProviderService svc = new ProviderService(providerRepository, modelRepository, null, null, null, null);
    Method m = ProviderService.class.getDeclaredMethod("matchImageProvider", String.class);
    m.setAccessible(true);
    assertThat(m.invoke(svc, new Object[]{null})).isNull();
}



    @Test
    // 覆盖 L348/L349：matchImageProvider || 链命中（qwen / 万相）与全不命中
    void testConnectionImageOrChainUnsupported() {
        MediaProvider qwen = saveProvider("qwen-img", "IMAGE");
        MediaProvider wanxiang = saveProvider("万相图片", "IMAGE");
        MediaProvider plain = saveProvider("plain pics", "IMAGE");
        assertThat(providerService.testConnection(qwen.getId()).status()).isEqualTo("UNSUPPORTED");
        assertThat(providerService.testConnection(wanxiang.getId()).status()).isEqualTo("UNSUPPORTED");
        assertThat(providerService.testConnection(plain.getId()).status()).isEqualTo("UNSUPPORTED");
    }
    // 覆盖 L356：matchMusicProvider name==null 防御分支（DB 有 NOT NULL 约束，public 路径不可达，改反射直测）
    @Test
    void testConnectionMusicNullNameUnsupported() throws Exception {
    ProviderService svc = new ProviderService(providerRepository, modelRepository, null, null, null, null);
    Method m = ProviderService.class.getDeclaredMethod("matchMusicProvider", String.class);
    m.setAccessible(true);
    assertThat(m.invoke(svc, new Object[]{null})).isNull();
}
    // 覆盖 L367：matchAvatarProvider name==null 防御分支（DB 有 NOT NULL 约束，public 路径不可达，改反射直测）
    @Test
    void testConnectionAvatarNullNameUnsupported() throws Exception {
    ProviderService svc = new ProviderService(providerRepository, modelRepository, null, null, null, null);
    Method m = ProviderService.class.getDeclaredMethod("matchAvatarProvider", String.class);
    m.setAccessible(true);
    assertThat(m.invoke(svc, new Object[]{null})).isNull();
}



    @Test
    // 覆盖 L371：matchAvatarProvider || 链命中（d-id / 数字人）与全不命中
    void testConnectionAvatarOrChainUnsupported() {
        MediaProvider did = saveProvider("did-talk", "AVATAR");
        MediaProvider digital = saveProvider("数字人厂商", "AVATAR");
        MediaProvider plain = saveProvider("plain avatar", "AVATAR");
        assertThat(providerService.testConnection(did.getId()).status()).isEqualTo("UNSUPPORTED");
        assertThat(providerService.testConnection(digital.getId()).status()).isEqualTo("UNSUPPORTED");
        assertThat(providerService.testConnection(plain.getId()).status()).isEqualTo("UNSUPPORTED");
    }

    @Test
    // 覆盖 L381：normalizeModule 的 module == null 回退、非法值回退、合法值保留
    void testCreateProviderNormalizeModuleBranches() {
        ProviderService.ProviderDto n1 = providerService.createProvider("n1", null, null, null, null);
        assertThat(n1.module()).isEqualTo("VIDEO");
        ProviderService.ProviderDto n2 = providerService.createProvider("n2", "NOPE", null, null, null);
        assertThat(n2.module()).isEqualTo("VIDEO");
        ProviderService.ProviderDto n3 = providerService.createProvider("n3", "IMAGE", null, null, null);
        assertThat(n3.module()).isEqualTo("IMAGE");
    }
}
