package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.VideoTask;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.FfmpegService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * MediaController 分支覆盖测试。
 *
 * 覆盖说明（JaCoCo 行号）：
 * - 81(4)：getVideo 成功 / task 不存在 / 文件不存在 / 路径穿越 —— 4 个测试。
 * - 110(4)：getFinal 成功 / 不存在 / 文件缺失 / 路径穿越 —— 4 个测试。
 * - 136(2)：loadSafe 的 !target.startsWith(base) —— true 臂由 getVideo_路径穿越 与 getFinal_路径穿越 覆盖；
 *           false 臂由 getVideo_成功 与 getFinal_成功 覆盖。
 * - 160(4)：getFinalPoster 缓存命中 / 缺失触发抽取 / 抽取抛异常 —— 3 个测试。
 * - 169(4)：getFinalPoster 尾部 exists 校验 —— 成功臂由缓存命中/抽取成功覆盖；
 *           !resource.exists() 臂由 getFinalPoster_抽取后文件仍缺失 覆盖。
 *
 * 诚实跳过清单：无（所有列出的分支均已覆盖）。
 */
class MediaControllerBranchTest {

    @TempDir
    Path tempDir;

    private VideoTaskRepository videoTaskRepository;
    private FinalCutRepository finalCutRepository;
    private FfmpegService ffmpegService;
    private MediaController controller;

    @BeforeEach
    void setUp() {
        videoTaskRepository = mock(VideoTaskRepository.class);
        finalCutRepository = mock(FinalCutRepository.class);
        ffmpegService = mock(FfmpegService.class);
        controller = new MediaController(tempDir.toString(), videoTaskRepository, finalCutRepository, ffmpegService);
    }

    // ---------- getVideo（覆盖第 81 行 4 个分支） ----------

    @Test
    void getVideo_success_returns200WithVideoMp4() throws IOException {
        // 覆盖第 74-90 行：findById 有值 → loadSafe 命中 base（136 false 臂）→ resource 存在可读 → 200 + video/mp4
        Path file = tempDir.resolve("video.mp4");
        Files.write(file, new byte[]{1, 2, 3});

        VideoTask task = new VideoTask();
        task.setLocalPath(file.toString());
        when(videoTaskRepository.findById(1L)).thenReturn(Optional.of(task));

        ResponseEntity<Resource> response = controller.getVideo(1L);

        assertEquals(200, response.getStatusCode().value());
        assertEquals(MediaType.parseMediaType("video/mp4"), response.getHeaders().getContentType());
        assertEquals("inline", response.getHeaders().getFirst("Content-Disposition"));
        assertNotNull(response.getBody());
    }

    @Test
    void getVideo_taskNotFound_throwsResourceNotFound() {
        // 覆盖第 74-75 行：findById 返回 Optional.empty() → orElseThrow 抛 ResourceNotFoundException
        when(videoTaskRepository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> controller.getVideo(99L));
    }

    @Test
    void getVideo_fileMissing_throwsResourceNotFound() {
        // 覆盖第 81 行 !resource.exists() 臂：路径合法但文件不存在
        Path missing = tempDir.resolve("missing.mp4");
        VideoTask task = new VideoTask();
        task.setLocalPath(missing.toString());
        when(videoTaskRepository.findById(2L)).thenReturn(Optional.of(task));

        assertThrows(ResourceNotFoundException.class, () -> controller.getVideo(2L));
    }

    @Test
    void getVideo_pathTraversal_throwsSecurityException() {
        // 覆盖第 136 行 !target.startsWith(base) true 臂：目标路径在 storageDir 之外
        VideoTask task = new VideoTask();
        task.setLocalPath("/etc/passwd");
        when(videoTaskRepository.findById(3L)).thenReturn(Optional.of(task));

        SecurityException ex = assertThrows(SecurityException.class, () -> controller.getVideo(3L));
        assertTrue(ex.getMessage().contains("非法文件路径"));
    }

    // ---------- getFinal（覆盖第 110 行 4 个分支） ----------

    @Test
    void getFinal_success_returns200WithVideoMp4() throws IOException {
        // 覆盖第 103-119 行：findById 有值 → loadSafe 命中 base → resource 存在可读 → 200 + video/mp4
        Path file = tempDir.resolve("final.mp4");
        Files.write(file, new byte[]{4, 5, 6});

        FinalCut cut = new FinalCut();
        cut.setFilePath(file.toString());
        when(finalCutRepository.findById(1L)).thenReturn(Optional.of(cut));

        ResponseEntity<Resource> response = controller.getFinal(1L);

        assertEquals(200, response.getStatusCode().value());
        assertEquals(MediaType.parseMediaType("video/mp4"), response.getHeaders().getContentType());
        assertEquals("inline", response.getHeaders().getFirst("Content-Disposition"));
        assertNotNull(response.getBody());
    }

    @Test
    void getFinal_notFound_throwsResourceNotFound() {
        // 覆盖第 103-104 行：findById 返回 Optional.empty() → orElseThrow 抛 ResourceNotFoundException
        when(finalCutRepository.findById(88L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class, () -> controller.getFinal(88L));
    }

    @Test
    void getFinal_fileMissing_throwsResourceNotFound() {
        // 覆盖第 110 行 !resource.exists() 臂：路径合法但文件不存在
        Path missing = tempDir.resolve("missing-final.mp4");
        FinalCut cut = new FinalCut();
        cut.setFilePath(missing.toString());
        when(finalCutRepository.findById(2L)).thenReturn(Optional.of(cut));

        assertThrows(ResourceNotFoundException.class, () -> controller.getFinal(2L));
    }

    @Test
    void getFinal_pathTraversal_throwsSecurityException() {
        // 覆盖第 136 行 !target.startsWith(base) true 臂（getFinal 入口）
        FinalCut cut = new FinalCut();
        cut.setFilePath("/etc/passwd");
        when(finalCutRepository.findById(3L)).thenReturn(Optional.of(cut));

        SecurityException ex = assertThrows(SecurityException.class, () -> controller.getFinal(3L));
        assertTrue(ex.getMessage().contains("非法文件路径"));
    }

    // ---------- getFinalPoster（覆盖第 160 / 169 行分支） ----------

    @Test
    void getFinalPoster_cachedPoster_returns200WithJpegWithoutExtracting() throws IOException {
        // 覆盖第 160 行 false 臂（海报已存在且是普通文件）→ 不调用 ffmpegService → 169 成功臂
        Path video = tempDir.resolve("cached.mp4");
        Files.write(video, new byte[]{7});
        Path poster = tempDir.resolve("cached.mp4.poster.jpg");
        Files.write(poster, new byte[]{(byte) 0xFF, (byte) 0xD8});

        FinalCut cut = new FinalCut();
        cut.setFilePath(video.toString());
        when(finalCutRepository.findById(10L)).thenReturn(Optional.of(cut));

        ResponseEntity<Resource> response = controller.getFinalPoster(10L);

        assertEquals(200, response.getStatusCode().value());
        assertEquals(MediaType.IMAGE_JPEG, response.getHeaders().getContentType());
        assertNotNull(response.getBody());
        verifyNoInteractions(ffmpegService);
    }

    @Test
    void getFinalPoster_posterMissing_extractsAndReturns200() throws IOException {
        // 覆盖第 160 行 true 臂 → extractPoster 成功创建文件 → 169 成功臂
        Path video = tempDir.resolve("need-extract.mp4");
        Files.write(video, new byte[]{8});
        Path poster = tempDir.resolve("need-extract.mp4.poster.jpg");

        FinalCut cut = new FinalCut();
        cut.setFilePath(video.toString());
        when(finalCutRepository.findById(11L)).thenReturn(Optional.of(cut));

        doAnswer(invocation -> {
            Path posterArg = invocation.getArgument(1);
            Files.createFile(posterArg);
            return null;
        }).when(ffmpegService).extractPoster(any(), any());

        ResponseEntity<Resource> response = controller.getFinalPoster(11L);

        assertEquals(200, response.getStatusCode().value());
        assertEquals(MediaType.IMAGE_JPEG, response.getHeaders().getContentType());
        verify(ffmpegService).extractPoster(eq(video), eq(poster));
    }

    @Test
    void getFinalPoster_extractThrows_throwsResourceNotFound() throws IOException {
        // 覆盖第 163-165 行 catch 分支：extractPoster 抛异常 → 转 ResourceNotFoundException
        Path video = tempDir.resolve("boom.mp4");
        Files.write(video, new byte[]{9});

        FinalCut cut = new FinalCut();
        cut.setFilePath(video.toString());
        when(finalCutRepository.findById(12L)).thenReturn(Optional.of(cut));

        doThrow(new RuntimeException("ffmpeg boom")).when(ffmpegService).extractPoster(any(), any());

        assertThrows(ResourceNotFoundException.class, () -> controller.getFinalPoster(12L));
    }

    @Test
    void getFinalPoster_extractNoOp_stillMissing_throwsResourceNotFound() throws IOException {
        // 覆盖第 169 行 !resource.exists() 臂：extractPoster 被调用但未创建文件
        Path video = tempDir.resolve("noop.mp4");
        Files.write(video, new byte[]{10});

        FinalCut cut = new FinalCut();
        cut.setFilePath(video.toString());
        when(finalCutRepository.findById(13L)).thenReturn(Optional.of(cut));

        doAnswer(invocation -> null).when(ffmpegService).extractPoster(any(), any());

        assertThrows(ResourceNotFoundException.class, () -> controller.getFinalPoster(13L));
    }
}
