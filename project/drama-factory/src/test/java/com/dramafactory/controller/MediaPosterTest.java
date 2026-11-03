package com.dramafactory.controller;

import com.dramafactory.service.FfmpegService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class MediaPosterTest {

    @Autowired
    private FfmpegService ffmpegService;

    @TempDir
    Path tempDir;

    @Test
    void extractPoster_generatesNonEmptyJpg() throws Exception {
        Path video = tempDir.resolve("test-clip.mp4");
        Path poster = tempDir.resolve("test-clip.mp4.poster.jpg");

        ffmpegService.generateTestClip(video, 2);

        assertTrue(Files.exists(video), "test clip should be generated");
        assertTrue(Files.size(video) > 0, "test clip should be non-empty");

        ffmpegService.extractPoster(video, poster);

        assertTrue(Files.exists(poster), "poster jpg should exist");
        assertTrue(Files.size(poster) > 0, "poster jpg should be non-empty");
    }
}
