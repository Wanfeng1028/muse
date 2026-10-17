package com.dramafactory.service;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.lang.reflect.Method;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

/**
 * v2.31 启动异常分类单元测试。
 */
class FfmpegLaunchClassifyV231Test {

    @Test
    void cannotAllocateMemoryIsTransient() {
        IOException e = new IOException("Cannot run program \"ffmpeg\": error=12, Cannot allocate memory");
        assertTrue(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    void tooManyOpenFilesIsTransient() {
        IOException e = new IOException("Too many open files");
        assertTrue(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    void resourceTemporarilyUnavailableIsTransient() {
        IOException e = new IOException("Resource temporarily unavailable");
        assertTrue(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    void noSuchFileIsPermanent() {
        IOException e = new IOException("Cannot run program \"ffmpeg\": error=2, No such file or directory");
        assertFalse(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    void permissionDeniedIsPermanent() {
        IOException e = new IOException("Cannot run program \"ffmpeg\": error=13, Permission denied");
        assertFalse(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    void accessDeniedIsPermanent() {
        IOException e = new IOException("Access is denied");
        assertFalse(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    void nullMessageIsPermanent() {
        IOException e = new IOException((String) null);
        assertFalse(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    void unknownMessageIsPermanent() {
        IOException e = new IOException("some weird unknown failure xyz");
        assertFalse(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    void emptyMessageIsPermanent() {
        IOException e = new IOException("");
        assertFalse(FfmpegService.isTransientLaunchFailure(e));
    }

    @Test
    @Timeout(value = 30, unit = TimeUnit.SECONDS)
    void realMissingBinaryIsPermanent() throws Exception {
        FfmpegService service = new FfmpegService("ffmpeg", "ffprobe");
        Method run = FfmpegService.class.getDeclaredMethod("run", List.class, long.class);
        run.setAccessible(true);
        FfmpegService.FfmpegException ex;
        try {
            run.invoke(service, List.of("drama-factory-nonexistent-bin-xyz"), 5L);
            throw new AssertionError("expected FfmpegException");
        } catch (java.lang.reflect.InvocationTargetException e) {
            assertTrue(e.getCause() instanceof FfmpegService.FfmpegException,
                    "cause 应为 FfmpegException，实际: " + e.getCause());
            ex = (FfmpegService.FfmpegException) e.getCause();
        }
        assertFalse(ex.isTransient());
    }
}
