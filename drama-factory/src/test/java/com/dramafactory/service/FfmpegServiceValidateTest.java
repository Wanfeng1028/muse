package com.dramafactory.service;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * FfmpegService.validateExecutable 白名单校验单测。
 */
class FfmpegServiceValidateTest {

    @Test
    void allowlistedBinaries_pass() {
        assertDoesNotThrow(
                () -> FfmpegService.validateExecutable(List.of("ffmpeg", "-version"), "ffmpeg", "ffprobe"),
                "ffmpeg 应在白名单内");
        assertDoesNotThrow(
                () -> FfmpegService.validateExecutable(List.of("ffprobe", "-version"), "ffmpeg", "ffprobe"),
                "ffprobe 应在白名单内");
    }

    @Test
    void evilBinary_rejected() {
        assertThrows(FfmpegService.FfmpegException.class,
                () -> FfmpegService.validateExecutable(List.of("/bin/evil", "-version"), "ffmpeg", "ffprobe"),
                "绝对路径恶意二进制应被拒");
        assertThrows(FfmpegService.FfmpegException.class,
                () -> FfmpegService.validateExecutable(List.of("ffmpeg-malicious", "-version"), "ffmpeg", "ffprobe"),
                "前缀欺骗应被拒（必须全等）");
    }

    @Test
    void emptyCommand_rejected() {
        assertThrows(FfmpegService.FfmpegException.class,
                () -> FfmpegService.validateExecutable(List.of(), "ffmpeg", "ffprobe"),
                "空命令应被拒");
    }
}
