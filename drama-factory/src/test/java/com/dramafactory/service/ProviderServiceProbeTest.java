package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.repository.ProviderModelRepository;
import com.dramafactory.service.video.VideoProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ProviderServiceProbeTest {

    private MediaProviderRepository providerRepository;
    private ProviderModelRepository modelRepository;

    @BeforeEach
    void setUp() {
        providerRepository = mock(MediaProviderRepository.class);
        modelRepository = mock(ProviderModelRepository.class);
    }

    private ProviderService serviceWith(Map<String, VideoProvider> providers) {
        return new ProviderService(providerRepository, modelRepository, providers);
    }

    private MediaProvider provider(Long id, String name, String module) {
        MediaProvider p = new MediaProvider();
        p.setId(id);
        p.setName(name);
        p.setModule(module);
        return p;
    }

    private void stubFind(MediaProvider p) {
        when(providerRepository.findById(p.getId())).thenReturn(Optional.of(p));
    }

    private VideoProvider stubVideoProvider(String name, VideoProvider.ConnectivityStatus status, String detail) {
        VideoProvider vp = mock(VideoProvider.class);
        when(vp.name()).thenReturn(name);
        when(vp.probeConnectivity()).thenReturn(new VideoProvider.ConnectivityResult(status, detail));
        return vp;
    }

    @Test
    void testConnection_providerNotFound_throws() {
        when(providerRepository.findById(99L)).thenReturn(Optional.empty());
        ProviderService service = serviceWith(Map.of());
        assertThrows(ResourceNotFoundException.class, () -> service.testConnection(99L));
    }

    @Test
    void testConnection_nonVideoModule_unsupported() {
        MediaProvider p = provider(1L, "img", "IMAGE");
        stubFind(p);
        ProviderService service = serviceWith(Map.of());
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertEquals("UNSUPPORTED", resp.status());
    }

    @Test
    void testConnection_videoModuleUnknownName_unsupported() {
        MediaProvider p = provider(1L, "unknown-xyz", "VIDEO");
        stubFind(p);
        ProviderService service = serviceWith(Map.of(
                "mock", stubVideoProvider("mock", VideoProvider.ConnectivityStatus.OK, "ok")));
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertEquals("UNSUPPORTED", resp.status());
    }

    @Test
    void testConnection_videoModuleNullName_unsupported() {
        MediaProvider p = provider(1L, null, "VIDEO");
        stubFind(p);
        ProviderService service = serviceWith(Map.of());
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertEquals("UNSUPPORTED", resp.status());
    }

    @Test
    void testConnection_agnesName_probesMatchedProvider() {
        MediaProvider p = provider(1L, "Agnes 主力", "VIDEO");
        stubFind(p);
        ProviderService service = serviceWith(Map.of(
                "agnes", stubVideoProvider("agnes", VideoProvider.ConnectivityStatus.OK, "ok"),
                "mock", stubVideoProvider("mock", VideoProvider.ConnectivityStatus.OK, "m")));
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertEquals("OK", resp.status());
        assertEquals("ok", resp.detail());
    }

    @Test
    void testConnection_dashscopeName_matchesQwen() {
        MediaProvider p = provider(1L, "dashscope 通义万相", "VIDEO");
        stubFind(p);
        ProviderService service = serviceWith(Map.of(
                "qwen", stubVideoProvider("qwen", VideoProvider.ConnectivityStatus.OK, "qok")));
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertEquals("OK", resp.status());
    }

    @Test
    void testConnection_mockName_matchesMock() {
        MediaProvider p = provider(1L, "mock 本地生成", "VIDEO");
        stubFind(p);
        ProviderService service = serviceWith(Map.of(
                "mock", stubVideoProvider("mock", VideoProvider.ConnectivityStatus.OK, "mok")));
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertEquals("OK", resp.status());
        assertEquals("mok", resp.detail());
    }

    @Test
    void testConnection_probeAuthFailed_passthrough() {
        MediaProvider p = provider(1L, "Agnes 主力", "VIDEO");
        stubFind(p);
        ProviderService service = serviceWith(Map.of(
                "agnes", stubVideoProvider("agnes", VideoProvider.ConnectivityStatus.AUTH_FAILED, "密钥无效")));
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertEquals("AUTH_FAILED", resp.status());
        assertEquals("密钥无效", resp.detail());
    }

    @Test
    void testConnection_checkedAtIsIsoLocalDateTime() {
        MediaProvider p = provider(1L, "Agnes 主力", "VIDEO");
        stubFind(p);
        ProviderService service = serviceWith(Map.of(
                "agnes", stubVideoProvider("agnes", VideoProvider.ConnectivityStatus.OK, "ok")));
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertTrue(resp.checkedAt().matches("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}.*"),
                "checkedAt should be ISO_LOCAL_DATE_TIME but was: " + resp.checkedAt());
    }

    @Test
    void testConnection_nullProvidersMap_noNpe() {
        MediaProvider p = provider(1L, "agnes x", "VIDEO");
        stubFind(p);
        ProviderService service = serviceWith(null);
        ProviderService.TestConnectionResponse resp = service.testConnection(1L);
        assertEquals("UNSUPPORTED", resp.status());
    }

    @Test
    void maskKey_null_returnsEmpty() {
        assertEquals("", ProviderService.maskKey(null));
    }

    @Test
    void maskKey_empty_returnsEmpty() {
        assertEquals("", ProviderService.maskKey(""));
    }

    @Test
    void maskKey_short_returnsDots() {
        assertEquals("••••", ProviderService.maskKey("abc"));
    }

    @Test
    void maskKey_long_masksMiddle() {
        assertEquals("sk••••3456", ProviderService.maskKey("sk-abcdef123456"));
    }
}
