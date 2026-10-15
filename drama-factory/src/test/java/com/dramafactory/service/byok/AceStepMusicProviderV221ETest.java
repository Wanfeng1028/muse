package com.dramafactory.service.byok;

import com.dramafactory.service.video.VideoProvider;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AceStepMusicProviderV221ETest {

    private final AceStepMusicProvider provider = new AceStepMusicProvider();

    @Test
    void generate_nullApiKey_throwsIllegalStateException() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate(null, "http://x", null, "p", null, false));
        assertEquals("未配置密钥：请先在通道管理填写该供应商的 API Key", ex.getMessage());
    }

    @Test
    void probe_nullApiKey_returnsAuthFailed() {
        MusicProvider.ConnectivityResult result = provider.probe(null, "http://x");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    @Test
    void generate_nullApiBase_throwsIllegalStateException() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", null, null, "p", null, false));
        assertEquals("未配置 API 地址：请先在通道管理填写该供应商的 API Base", ex.getMessage());
    }
}
