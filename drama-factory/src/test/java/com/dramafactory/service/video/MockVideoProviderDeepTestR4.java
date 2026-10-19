package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MockVideoProviderDeepTestR4 {

    @Test
    void submit_twoJobs_idsDifferent() {
        MockVideoProvider provider = new MockVideoProvider();
        Shot shot = new Shot();
        String id1 = provider.submit(shot, 5);
        String id2 = provider.submit(shot, 5);
        assertNotEquals(id1, id2);
        assertTrue(id1.startsWith("mock-"));
        assertTrue(id2.startsWith("mock-"));
    }

    @Test
    void submit_nullShot_ok() {
        MockVideoProvider provider = new MockVideoProvider();
        String id = provider.submit(null, 5);
        assertNotNull(id);
        assertTrue(id.startsWith("mock-"));
    }

    @Test
    void poll_readyAfterMsZero_immediatelyCompleted() {
        MockVideoProvider provider = new MockVideoProvider();
        provider.setReadyAfterMs(0L);
        String id = provider.submit(new Shot(), 5);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
    }

    @Test
    void poll_completed_videoUrlContainsSeconds() {
        MockVideoProvider provider = new MockVideoProvider();
        provider.setReadyAfterMs(0L);
        String id = provider.submit(new Shot(), 7);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertEquals("mock://clip?seconds=7", result.videoUrl());
    }

    @Test
    void poll_completed_progress100() {
        MockVideoProvider provider = new MockVideoProvider();
        provider.setReadyAfterMs(0L);
        String id = provider.submit(new Shot(), 5);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertEquals(100, result.progress());
        assertNull(result.errorMessage());
    }

    @Test
    void poll_processing_progress50() {
        MockVideoProvider provider = new MockVideoProvider();
        String id = provider.submit(new Shot(), 5);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertTrue(result.status() == VideoProvider.RemoteStatus.PROCESSING
                || result.status() == VideoProvider.RemoteStatus.QUEUED);
        assertEquals(50, result.progress());
        assertNull(result.videoUrl());
    }

    @Test
    void poll_failNext_onlyOnce() {
        MockVideoProvider provider = new MockVideoProvider();
        String id = provider.submit(new Shot(), 5);
        provider.setFailNext(true);
        VideoProvider.ProbeResult first = provider.poll(id);
        assertEquals(VideoProvider.RemoteStatus.FAILED, first.status());
        assertEquals("mock 模拟失败", first.errorMessage());
        VideoProvider.ProbeResult second = provider.poll(id);
        assertNotEquals(VideoProvider.RemoteStatus.FAILED, second.status());
    }

    @Test
    void poll_failNext_beatsReady() {
        MockVideoProvider provider = new MockVideoProvider();
        provider.setReadyAfterMs(0L);
        String id = provider.submit(new Shot(), 5);
        provider.setFailNext(true);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
    }

    @Test
    void poll_unknownId_messageContainsId() {
        MockVideoProvider provider = new MockVideoProvider();
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> provider.poll("nope-123"));
        assertTrue(ex.getMessage().contains("nope-123"));
    }

    @Test
    void probeConnectivity_returnsOk() {
        MockVideoProvider provider = new MockVideoProvider();
        VideoProvider.ConnectivityResult result = provider.probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
        assertEquals("演示用提供方，无需真实连接", result.detail());
    }

    @Test
    void setReadyAfterMs_negative_immediatelyCompleted() {
        MockVideoProvider provider = new MockVideoProvider();
        provider.setReadyAfterMs(-1L);
        String id = provider.submit(new Shot(), 5);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
    }

    @Test
    void jobs_isolatedBetweenProviders() {
        MockVideoProvider providerA = new MockVideoProvider();
        MockVideoProvider providerB = new MockVideoProvider();
        String id = providerA.submit(new Shot(), 5);
        assertThrows(IllegalArgumentException.class, () -> providerB.poll(id));
    }
}