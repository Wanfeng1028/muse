package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AgnesVideoProviderV222ETest {

    @Mock
    private CredentialResolver credentialResolver;

    @Mock
    private VideoHttpGateway gateway;

    private AgnesVideoProvider newProvider() {
        when(credentialResolver.agnesAuth(any()))
                .thenReturn(Map.entry("Authorization", "Bearer test-key"));
        return new AgnesVideoProvider(credentialResolver, gateway);
    }

    @Test
    void probeConnectivity_codeBelow200_returnsProviderError() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(199, "x"));

        VideoProvider.ConnectivityResult result = provider.probeConnectivity();

        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, result.status());
    }

    @Test
    void submit_idNodeExplicitNull_throwsRuntimeException() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200, "{\"video_id\":null,\"id\":null}"));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit(new Shot(), 5));
        assertTrue(ex.getMessage().contains("缺少 video_id/id 字段"));
    }

    @Test
    void poll_completed_metadataUrlPresent_usesMetadataUrl() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200,
                        "{\"status\":\"completed\",\"metadata\":{\"url\":\"http://m/y.mp4\"},\"url\":\"http://v/x.mp4\"}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertEquals("http://m/y.mp4", result.videoUrl());
    }

    @Test
    void poll_completed_metadataUrlAbsent_fallsBackToTopLevelUrl() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200,
                        "{\"status\":\"completed\",\"metadata\":{},\"url\":\"http://v/x.mp4\"}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertEquals("http://v/x.mp4", result.videoUrl());
    }

    @Test
    void poll_completed_topLevelUrlExplicitNull_videoUrlNull() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200,
                        "{\"status\":\"completed\",\"url\":null}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertNull(result.videoUrl());
    }

    @Test
    void poll_failed_errorExplicitNull_errorMessageNull() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200,
                        "{\"status\":\"failed\",\"error\":null}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
        assertNull(result.errorMessage());
    }
}
