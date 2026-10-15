package com.dramafactory.service.video;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
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
class AgnesVideoProviderV222CTest {

    @Mock
    private CredentialResolver credentialResolver;

    @Mock
    private VideoHttpGateway gateway;

    private AgnesVideoProvider newProvider() {
        when(credentialResolver.agnesAuth(any()))
                .thenReturn(Map.entry("Authorization", "Bearer test-key"));
        return new AgnesVideoProvider(credentialResolver, gateway);
    }

    private static Shot blankPromptShot() {
        Shot shot = new Shot();
        shot.setVideoPrompt("   ");
        shot.setDescription("雨夜");
        shot.setShotSize(ShotSize.TE_XIE);
        shot.setCameraMove(CameraMove.GU_DING);
        return shot;
    }

    // ① probe：2xx 真臂
    @Test
    void probeConnectivity_returnsOk_when2xx() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200, "{}"));

        VideoProvider.ConnectivityResult result = provider.probeConnectivity();

        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
    }

    // ② probe：非 2xx 假臂
    @Test
    void probeConnectivity_returnsProviderError_when500() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(500, "err"));

        VideoProvider.ConnectivityResult result = provider.probeConnectivity();

        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, result.status());
    }

    // ③ submit：blank 臂拼接 + video_id 返回
    @Test
    void submit_usesConcatenatedPrompt_whenVideoPromptBlank() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200, "{\"video_id\":\"v1\"}"));

        String id = provider.submit(blankPromptShot(), 5);

        assertEquals("v1", id);
    }

    // ④ submit：status<200 臂
    @Test
    void submit_throws_whenStatus199() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(199, "x"));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit(blankPromptShot(), 5));
        assertTrue(ex.getMessage().contains("199"));
    }

    // ⑤ submit：body 为 null 臂
    @Test
    void submit_throws_whenStatus500AndNullBody() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(500, null));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit(blankPromptShot(), 5));
        assertTrue(ex.getMessage().contains("500"));
    }

    // ⑥ submit：video_id 显式 null，回退 id
    @Test
    void submit_fallsBackToId_whenVideoIdIsNull() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200, "{\"video_id\":null,\"id\":\"abc\"}"));

        String id = provider.submit(blankPromptShot(), 5);

        assertEquals("abc", id);
    }

    // ⑦ submit：双缺失抛异常
    @Test
    void submit_throws_whenNoIdFields() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200, "{\"foo\":\"bar\"}"));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit(blankPromptShot(), 5));
        assertTrue(ex.getMessage().contains("缺少 video_id/id 字段"));
    }

    // ⑧ poll：status<200 臂
    @Test
    void poll_throws_whenStatus199() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(199, "x"));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("task-1"));
        assertTrue(ex.getMessage().contains("199"));
    }

    // ⑨ poll：metadata 显式 null，回退顶层 url
    @Test
    void poll_completed_usesTopLevelUrl_whenMetadataNull() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200,
                        "{\"status\":\"completed\",\"metadata\":null,\"url\":\"http://v/x.mp4\"}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertEquals("http://v/x.mp4", result.videoUrl());
    }

    // ⑩ poll：metadata.url 显式 null，回退顶层 url
    @Test
    void poll_completed_usesTopLevelUrl_whenMetadataUrlNull() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200,
                        "{\"status\":\"completed\",\"metadata\":{\"url\":null},\"url\":\"http://v/x.mp4\"}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertEquals("http://v/x.mp4", result.videoUrl());
    }

    // ⑪ poll：无 url 字段，videoUrl 为 null
    @Test
    void poll_completed_videoUrlNull_whenNoUrlField() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200, "{\"status\":\"completed\"}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertNull(result.videoUrl());
    }

    // ⑫ poll：failed，message 显式 null，回退 error
    @Test
    void poll_failed_usesError_whenMessageNull() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200,
                        "{\"status\":\"failed\",\"message\":null,\"error\":\"boom\"}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
        assertEquals("boom", result.errorMessage());
    }

    // ⑬ poll：failed，无 message 无 error
    @Test
    void poll_failed_errorMessageNull_whenNoMessageNoError() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200, "{\"status\":\"failed\"}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
        assertNull(result.errorMessage());
    }

    // ⑭ poll：processing，progress 显式 null
    @Test
    void poll_processing_progressZero_whenProgressNull() throws Exception {
        AgnesVideoProvider provider = newProvider();
        when(gateway.exchange(any()))
                .thenReturn(new VideoHttpGateway.GatewayResponse(200,
                        "{\"status\":\"processing\",\"progress\":null}"));

        VideoProvider.ProbeResult result = provider.poll("task-1");

        assertEquals(VideoProvider.RemoteStatus.PROCESSING, result.status());
        assertEquals(0, result.progress());
    }
}
