package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.FfmpegService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * ChunkedVideoWorkflow 单元测试：用 mock provider，全程无网络。
 */
class ChunkedVideoWorkflowTest {

    private VideoProviderRouter router;
    private FfmpegService ffmpegService;
    private VideoProvider mockProvider;
    private ChunkedVideoWorkflow workflow;

    @BeforeEach
    void setUp() {
        router = mock(VideoProviderRouter.class);
        ffmpegService = mock(FfmpegService.class);
        mockProvider = mock(VideoProvider.class);
        // poll 间隔 1ms、超时 5s，测试跑得快
        workflow = new ChunkedVideoWorkflow(router, ffmpegService, 1L, 5000L);
    }

    private Shot newShot(long id, String desc) {
        Shot shot = new Shot();
        shot.setId(id);
        shot.setDescription(desc);
        return shot;
    }

    private VideoProvider.ProbeResult completed(String url) {
        return new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.COMPLETED, url, null, 100);
    }

    @Test
    void run_allChunksSucceed() {
        when(router.providerFor("minimax")).thenReturn(mockProvider);
        when(mockProvider.submit(anyShot(), anyInt())).thenReturn("task-1", "task-2");
        when(mockProvider.poll("task-1"))
                .thenReturn(new VideoProvider.ProbeResult(
                        VideoProvider.RemoteStatus.PROCESSING, null, null, 50))
                .thenReturn(completed("http://cdn/1.mp4"));
        when(mockProvider.poll("task-2")).thenReturn(completed("http://cdn/2.mp4"));

        List<ChunkedVideoWorkflow.ChunkResult> results = workflow.run(
                List.of(newShot(1L, "A"), newShot(2L, "B")), "minimax", 6);

        assertEquals(2, results.size());
        assertTrue(results.get(0).succeeded());
        assertTrue(results.get(1).succeeded());
        assertEquals("http://cdn/1.mp4", results.get(0).videoUrl());
        assertEquals("http://cdn/2.mp4", results.get(1).videoUrl());
    }

    @Test
    void run_chunkFailed_markedFailed() {
        when(router.providerFor("minimax")).thenReturn(mockProvider);
        when(mockProvider.submit(anyShot(), anyInt())).thenReturn("task-9");
        when(mockProvider.poll("task-9")).thenReturn(new VideoProvider.ProbeResult(
                VideoProvider.RemoteStatus.FAILED, null, "内容审核未通过", 0));

        List<ChunkedVideoWorkflow.ChunkResult> results = workflow.run(
                List.of(newShot(9L, "X")), "minimax", 6);

        assertEquals(1, results.size());
        assertTrue(!results.get(0).succeeded());
        assertTrue(results.get(0).errorMessage().contains("内容审核未通过"));
    }

    @Test
    void retryChunk_resubmitsSingleChunk() {
        when(router.providerFor("minimax")).thenReturn(mockProvider);
        when(mockProvider.submit(anyShot(), anyInt())).thenReturn("task-retry");
        when(mockProvider.poll("task-retry")).thenReturn(completed("http://cdn/retry.mp4"));

        ChunkedVideoWorkflow.ChunkResult result =
                workflow.retryChunk(1, newShot(5L, "R"), "minimax", 6);

        assertTrue(result.succeeded());
        assertEquals(1, result.index());
        assertEquals("http://cdn/retry.mp4", result.videoUrl());
    }

    @Test
    void run_emptyShots_returnsEmpty() {
        assertTrue(workflow.run(List.of(), "minimax", 6).isEmpty());
    }

    @Test
    void run_nullProviderName_usesRouterChain() {
        VideoProviderRouter.RouteResult route =
                new VideoProviderRouter.RouteResult("minimax", "task-chain", null);
        when(router.submit(anyShot(), eq(6))).thenReturn(route);
        when(router.providerFor("minimax")).thenReturn(mockProvider);
        when(mockProvider.poll("task-chain")).thenReturn(completed("http://cdn/c.mp4"));

        List<ChunkedVideoWorkflow.ChunkResult> results =
                workflow.run(List.of(newShot(3L, "C")), null, 6);

        assertEquals(1, results.size());
        assertTrue(results.get(0).succeeded());
        assertEquals("minimax", results.get(0).providerName());
    }

    @Test
    void assemble_withFailedChunk_throws() {
        ChunkedVideoWorkflow.ChunkResult failed = new ChunkedVideoWorkflow.ChunkResult(
                0, 1L, "minimax", "t", null,
                VideoProvider.RemoteStatus.FAILED, "boom");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> workflow.assemble(List.of(failed),
                        java.nio.file.Path.of("/tmp/w"), java.nio.file.Path.of("/tmp/w/out.mp4")));
        assertTrue(ex.getMessage().contains("retryChunk"), "实际: " + ex.getMessage());
    }

    private static Shot anyShot() {
        return org.mockito.ArgumentMatchers.any(Shot.class);
    }
}
