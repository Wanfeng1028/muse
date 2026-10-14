// ffmpeg 二进制缺失的失败注入测试（DoD G1）。
package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class FfmpegServiceMissingBinaryTest {

    @Test
    void missingBinary_generateTestClip_throwsFfmpegException(@TempDir Path tempDir) {
        FfmpegService service = new FfmpegService("nonexistent-ffmpeg-xyz-12345", "nonexistent-ffprobe-xyz-12345");

        FfmpegService.FfmpegException ex = assertThrows(
                FfmpegService.FfmpegException.class,
                () -> service.generateTestClip(tempDir.resolve("out.mp4"), 1));

        assertTrue(ex.getMessage().contains("无法启动命令"), "message 应包含 '无法启动命令'，实际: " + ex.getMessage());
        assertTrue(ex.getMessage().contains("nonexistent-ffmpeg-xyz-12345"), "message 应包含缺失的 ffmpeg 二进制名，实际: " + ex.getMessage());
    }

    @Test
    void missingBinary_probeDuration_throwsFfmpegException(@TempDir Path tempDir) {
        FfmpegService service = new FfmpegService("nonexistent-ffmpeg-xyz-12345", "nonexistent-ffprobe-xyz-12345");

        FfmpegService.FfmpegException ex = assertThrows(
                FfmpegService.FfmpegException.class,
                () -> service.probeDurationSeconds(tempDir.resolve("in.mp4")));

        assertTrue(ex.getMessage().contains("无法启动 ffprobe"), "message 应包含 '无法启动 ffprobe'，实际: " + ex.getMessage());
        assertTrue(ex.getMessage().contains("nonexistent-ffprobe-xyz-12345"), "message 应包含缺失的 ffprobe 二进制名，实际: " + ex.getMessage());
    }
}
