package com.dramafactory.controller;

/*
 * 覆盖说明（行号对应 MediaController.java）：
 * - 第 81 行  getVideo: !resource.isReadable() 为 true 分支
 *       -> getVideo_existingDirectoryNotReadable_throwsResourceNotFound
 * - 第 110 行 getFinal: !resource.isReadable() 为 true 分支
 *       -> getFinal_existingDirectoryNotReadable_throwsResourceNotFound
 * - 第 160 行 getFinalPoster: !Files.isRegularFile(posterPath) 为 true 分支
 *   与 第 169 行 !resource.isReadable() 为 true 分支
 *       -> getFinalPoster_posterPathIsDirectory_notReadable_throwsResourceNotFound
 */

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.VideoTask;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.FfmpegService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class MediaControllerBranch2Test {

    @TempDir
    Path tempDir;

    @Test
    void getVideo_existingDirectoryNotReadable_throwsResourceNotFound() {
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        FinalCutRepository finalCutRepository = mock(FinalCutRepository.class);
        FfmpegService ffmpegService = mock(FfmpegService.class);

        MediaController controller = new MediaController(
                tempDir.toString(), videoTaskRepository, finalCutRepository, ffmpegService);

        Path directoryPath = Paths.get(tempDir.toString(), "video-dir");
        try {
            Files.createDirectory(directoryPath);
        } catch (Exception ex) {
            throw new RuntimeException(ex);
        }

        VideoTask task = new VideoTask();
        task.setLocalPath(directoryPath.toString());

        Optional<VideoTask> stubResult = Optional.of(task);
        when(videoTaskRepository.findById(11L)).thenReturn(stubResult);

        assertThrows(ResourceNotFoundException.class, () -> controller.getVideo(11L));
    }

    @Test
    void getFinal_existingDirectoryNotReadable_throwsResourceNotFound() {
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        FinalCutRepository finalCutRepository = mock(FinalCutRepository.class);
        FfmpegService ffmpegService = mock(FfmpegService.class);

        MediaController controller = new MediaController(
                tempDir.toString(), videoTaskRepository, finalCutRepository, ffmpegService);

        Path directoryPath = Paths.get(tempDir.toString(), "final-dir");
        try {
            Files.createDirectory(directoryPath);
        } catch (Exception ex) {
            throw new RuntimeException(ex);
        }

        FinalCut cut = new FinalCut();
        cut.setFilePath(directoryPath.toString());

        Optional<FinalCut> stubResult = Optional.of(cut);
        when(finalCutRepository.findById(12L)).thenReturn(stubResult);

        assertThrows(ResourceNotFoundException.class, () -> controller.getFinal(12L));
    }

    @Test
    void getFinalPoster_posterPathIsDirectory_notReadable_throwsResourceNotFound() {
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        FinalCutRepository finalCutRepository = mock(FinalCutRepository.class);
        FfmpegService ffmpegService = mock(FfmpegService.class);

        MediaController controller = new MediaController(
                tempDir.toString(), videoTaskRepository, finalCutRepository, ffmpegService);

        Path videoPath = Paths.get(tempDir.toString(), "video.mp4");
        try {
            Files.write(videoPath, new byte[]{1, 2, 3});
        } catch (Exception ex) {
            throw new RuntimeException(ex);
        }

        Path posterPath = Paths.get(tempDir.toString(), "video.mp4.poster.jpg");
        try {
            Files.createDirectory(posterPath);
        } catch (Exception ex) {
            throw new RuntimeException(ex);
        }

        FinalCut cut = new FinalCut();
        cut.setFilePath(videoPath.toString());

        Optional<FinalCut> stubResult = Optional.of(cut);
        when(finalCutRepository.findById(13L)).thenReturn(stubResult);

        try {
            doNothing().when(ffmpegService).extractPoster(any(Path.class), any(Path.class));
        } catch (Exception ex) {
            throw new RuntimeException(ex);
        }

        assertThrows(ResourceNotFoundException.class, () -> controller.getFinalPoster(13L));
    }
}
