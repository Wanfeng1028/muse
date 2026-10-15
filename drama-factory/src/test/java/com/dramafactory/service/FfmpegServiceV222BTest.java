package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * FfmpegService 补覆盖测试（针对 jacoco missed-branch 清单）。
 *
 * 诚实跳过清单：
 * 1) L313 probeDurationSeconds 内 `if (!finished)` —— waitFor 写死 60 秒，
 *    无法在确定性、秒级完成的测试中触发该超时臂，跳过。
 * 2) L325 ffprobe 失败分支中的长输出臂（out.length() > 500）—— 该分支的
 *    长输出依赖真实 ffprobe 的 stderr 协议输出格式，单 token 假命令无法复现，
 *    诚实记为不可达，仅覆盖短输出臂。
 */
class FfmpegServiceV222BTest {

    private void invokeRun(FfmpegService service, List<String> cmd, long timeoutSeconds) throws Exception {
        Method m = FfmpegService.class.getDeclaredMethod("run", List.class, long.class);
        m.setAccessible(true);
        try {
            m.invoke(service, cmd, timeoutSeconds);
        } catch (java.lang.reflect.InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause instanceof RuntimeException) {
                throw (RuntimeException) cause;
            }
            throw e;
        }
    }

    // L113: 命令超时臂
    @Test
    void run_timeoutBranch_throwsFfmpegException() throws Exception {
        FfmpegService service = new FfmpegService("ffmpeg", "ffprobe");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> invokeRun(service, List.of("sleep", "30"), 0L));
        assertTrue(ex.getMessage().contains("超时"),
                "超时异常 message 应包含 '超时'，实际: " + ex.getMessage());
    }

    // L125 + L127 短输出臂：非零退出且输出 <= 500
    @Test
    void run_nonZeroExit_shortOutput_throwsWithExitCode() throws Exception {
        FfmpegService service = new FfmpegService("ffmpeg", "ffprobe");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> invokeRun(service, List.of("sh", "-c", "echo hi; exit 3"), 30L));
        assertTrue(ex.getMessage().contains("退出码 3"),
                "异常 message 应包含 '退出码 3'，实际: " + ex.getMessage());
    }

    // L125 + L127 长输出臂：非零退出且输出 > 500
    @Test
    void run_nonZeroExit_longOutput_truncatedSnippet() throws Exception {
        FfmpegService service = new FfmpegService("ffmpeg", "ffprobe");
        String script = "i=0; while [ $i -lt 600 ]; do printf 'x'; i=$((i+1)); done; echo; exit 3";
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> invokeRun(service, List.of("sh", "-c", script), 30L));
        String msg = ex.getMessage();
        assertTrue(msg.contains("退出码 3"),
                "异常 message 应包含 '退出码 3'，实际: " + msg);
        assertTrue(msg.contains("输出: "),
                "异常 message 应包含 '输出: '，实际: " + msg);
        int idx = msg.indexOf("输出: ");
        String snippet = msg.substring(idx + "输出: ".length());
        assertTrue(snippet.length() <= 501,
                "截断后片段长度应 <= 501，实际: " + snippet.length());
    }

    // L142: generateTestClip 内 parent == null 臂
    @Test
    void generateTestClip_parentNull_skipsMkdirAndFailsOnFalse() {
        FfmpegService service = new FfmpegService("false", "false");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.generateTestClip(Path.of("no-parent-xyz.mp4"), 1));
        assertTrue(ex.getMessage().contains("退出码") || ex.getMessage().contains("失败"),
                "异常 message 应反映命令失败，实际: " + ex.getMessage());
    }

    // L174: inputs == null 臂
    @Test
    void concatClips_nullInputs_throwsEmptyList() {
        FfmpegService service = new FfmpegService("ffmpeg", "ffprobe");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.concatClips(null, Path.of("o.mp4")));
        assertTrue(ex.getMessage().contains("不能为空"),
                "异常 message 应包含 '不能为空'，实际: " + ex.getMessage());
    }

    // L174: inputs.isEmpty() 臂
    @Test
    void concatClips_emptyInputs_throwsEmptyList() {
        FfmpegService service = new FfmpegService("ffmpeg", "ffprobe");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.concatClips(List.of(), Path.of("o.mp4")));
        assertTrue(ex.getMessage().contains("不能为空"),
                "异常 message 应包含 '不能为空'，实际: " + ex.getMessage());
    }

    // L179: concatClips 内 parent == null 臂
    @Test
    void concatClips_outputWithoutParent_throwsMissingParent() {
        FfmpegService service = new FfmpegService("ffmpeg", "ffprobe");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.concatClips(List.of(Path.of("a.mp4")), Path.of("o.mp4")));
        assertTrue(ex.getMessage().contains("缺少父目录"),
                "异常 message 应包含 '缺少父目录'，实际: " + ex.getMessage());
    }

    // L240: burnSubtitles 内 parent == null 臂
    @Test
    void burnSubtitles_outputWithoutParent_throwsMissingParent() {
        FfmpegService service = new FfmpegService("ffmpeg", "ffprobe");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.burnSubtitles(Path.of("a.mp4"), Path.of("a.srt"), Path.of("o.mp4")));
        assertTrue(ex.getMessage().contains("缺少父目录"),
                "异常 message 应包含 '缺少父目录'，实际: " + ex.getMessage());
    }

    // L421: extractAudio 内 "wav".equalsIgnoreCase 臂
    @Test
    void extractAudio_wavFormat_reachesWavBranchThenFails(@TempDir Path dir) {
        FfmpegService service = new FfmpegService("false", "false");
        Path input = dir.resolve("in.mp4");
        Path output = dir.resolve("out.wav");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.extractAudio(input, output, "wav"));
        assertTrue(ex.getMessage().contains("退出码"),
                "异常 message 应包含 '退出码'，实际: " + ex.getMessage());
    }

    // L330: probeDurationSeconds 内 raw.isEmpty() 臂
    @Test
    void probeDurationSeconds_emptyOutput_throwsNoDuration(@TempDir Path dir) {
        FfmpegService service = new FfmpegService("ffmpeg", "true");
        Path file = dir.resolve("any.bin");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.probeDurationSeconds(file));
        assertTrue(ex.getMessage().contains("未返回时长信息"),
                "异常 message 应包含 '未返回时长信息'，实际: " + ex.getMessage());
    }

    // L325 短输出臂：ffprobe 非零退出且输出为空
    @Test
    void probeDurationSeconds_nonZeroExit_shortOutput_throwsFfprobeFailed(@TempDir Path dir) {
        FfmpegService service = new FfmpegService("ffmpeg", "false");
        Path file = dir.resolve("any.bin");
        FfmpegService.FfmpegException ex = assertThrows(FfmpegService.FfmpegException.class,
                () -> service.probeDurationSeconds(file));
        assertTrue(ex.getMessage().contains("ffprobe 执行失败"),
                "异常 message 应包含 'ffprobe 执行失败'，实际: " + ex.getMessage());
    }
}
