package com.dramafactory.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import org.junit.jupiter.api.Test;

/**
 * v2.29 flaky 根因歼灭——ffmpeg 瞬时/永久分类契约测试。
 *
 * <p>验证 {@link FfmpegService.FfmpegException} 的 transientFailure 语义：
 * 瞬时失败（超时、被信号杀死）应标记为 transient，永久失败（无法启动）应标记为 permanent，
 * 旧构造器保守默认为 transient。</p>
 */
class FfmpegExceptionClassificationTest {

    @Test
    void timeoutIsTransient() {
        String message = "命令超时(120s): ffmpeg -y -i a.mp4";
        FfmpegService.FfmpegException ex = new FfmpegService.FfmpegException(message, true);
        assertTrue(ex.isTransient(), "超时属于瞬时失败，isTransient() 应为 true");
        assertEquals(message, ex.getMessage(), "getMessage() 应原样保留传入的消息");
    }

    @Test
    void killedBySignalIsTransient() {
        FfmpegService.FfmpegException ex =
                new FfmpegService.FfmpegException("命令执行失败(退出码 137): ffmpeg", true);
        assertTrue(ex.isTransient(), "被信号杀死(退出码 137)属于瞬时失败，isTransient() 应为 true");
    }

    @Test
    void cannotStartIsPermanent() {
        FfmpegService.FfmpegException ex =
                new FfmpegService.FfmpegException("无法启动命令: ffmpeg", new IOException("error=2"), false);
        assertEquals(false, ex.isTransient(), "无法启动属于永久失败，isTransient() 应为 false");
    }

    @Test
    void legacyConstructorsDefaultToTransient() {
        FfmpegService.FfmpegException oneArg = new FfmpegService.FfmpegException("oops");
        assertTrue(oneArg.isTransient(), "旧单参构造器应保守默认为 transient");

        FfmpegService.FfmpegException twoArg =
                new FfmpegService.FfmpegException("oops", new RuntimeException("x"));
        assertTrue(twoArg.isTransient(), "旧双参构造器应保守默认为 transient");
    }

    @Test
    void isRuntimeException() {
        RuntimeException caught = assertThrows(RuntimeException.class, () -> {
            throw new FfmpegService.FfmpegException("boom", true);
        });
        assertInstanceOf(FfmpegService.FfmpegException.class, caught,
                "FfmpegException 应是 RuntimeException 的子类，可被 catch (RuntimeException e) 捕获");
    }
}
