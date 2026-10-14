
package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * MockVideoProvider 的单元测试：纯内存，无外部依赖。
 */
class MockVideoProviderTest {

    private Shot newShot() {
        return new Shot();
    }

    @Test
    void submit_returnsMockPrefixedId() {
        MockVideoProvider provider = new MockVideoProvider();
        String id = provider.submit(newShot(), 5);
        assertNotNull(id);
        assertTrue(id.startsWith("mock-"));
    }

    @Test
    void poll_immediatelyAfterSubmitIsProcessingOrQueued() {
        MockVideoProvider provider = new MockVideoProvider();
        provider.setReadyAfterMs(10_000L);
        String id = provider.submit(newShot(), 5);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertTrue(result.status() == VideoProvider.RemoteStatus.QUEUED
                        || result.status() == VideoProvider.RemoteStatus.PROCESSING,
                "刚提交应处于 QUEUED 或 PROCESSING，实际: " + result.status());
    }

    @Test
    void poll_afterReadyIsCompleted() {
        MockVideoProvider provider = new MockVideoProvider();
        provider.setReadyAfterMs(0L);
        String id = provider.submit(newShot(), 5);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertNotNull(result.videoUrl());
        assertTrue(result.videoUrl().length() > 0);
    }

    @Test
    void poll_failNextReturnsFailed() {
        MockVideoProvider provider = new MockVideoProvider();
        String id = provider.submit(newShot(), 5);
        provider.setFailNext(true);
        VideoProvider.ProbeResult result = provider.poll(id);
        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
        assertNotNull(result.errorMessage());
    }

    @Test
    void poll_unknownIdThrows() {
        MockVideoProvider provider = new MockVideoProvider();
        assertThrows(IllegalArgumentException.class, () -> provider.poll("mock-不存在的id"));
    }

    @Test
    void name_isMock() {
        MockVideoProvider provider = new MockVideoProvider();
        assertEquals("mock", provider.name());
    }
}
