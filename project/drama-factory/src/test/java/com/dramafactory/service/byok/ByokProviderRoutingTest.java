
package com.dramafactory.service.byok;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class ByokProviderRoutingTest {

    @Test
    void imageRoutesDashscope() {
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("dashscope 万相"));
    }

    @Test
    void imageRoutesQwen() {
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("qwen-image"));
    }

    @Test
    void imageRoutesWanxiang() {
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("万相"));
    }

    @Test
    void imageUnknownReturnsNull() {
        assertNull(ByokGenerateService.matchImage("unknown-xyz"));
    }

    @Test
    void musicRoutesMinimax() {
        assertEquals("minimaxmusicprovider", ByokGenerateService.matchMusic("minimax music"));
    }

    @Test
    void musicRoutesAceStep() {
        assertEquals("acestepmusicprovider", ByokGenerateService.matchMusic("ace-step-test"));
    }

    @Test
    void musicRoutesAceStepCompact() {
        assertEquals("acestepmusicprovider", ByokGenerateService.matchMusic("acestep"));
    }

    @Test
    void musicUnknownReturnsNull() {
        assertNull(ByokGenerateService.matchMusic("suno"));
    }

    @Test
    void avatarRoutesDid() {
        assertEquals("didavatarprovider", ByokGenerateService.matchAvatar("d-id talks"));
    }

    @Test
    void avatarRoutesShuziren() {
        assertEquals("didavatarprovider", ByokGenerateService.matchAvatar("数字人"));
    }

    @Test
    void avatarUnknownReturnsNull() {
        assertNull(ByokGenerateService.matchAvatar("heygen"));
    }
}
