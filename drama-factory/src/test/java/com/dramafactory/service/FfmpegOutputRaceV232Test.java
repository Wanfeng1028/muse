package com.dramafactory.service;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * FfmpegService 输出竞态修复（B2-FIX2）的行为契约测试。
 *
 * 覆盖点：
 *  - 用例 a：慢速小输出 + 非零退出码，进程退出后 snippet 仍含尾部标记，且总输出 <500 字符。
 *            这是修复后的行为契约；旧代码在低概率时序下会丢失尾部输出，因此该用例
 *            是对新契约的确定性验证，而非对旧缺陷的稳定复现。
 *  - 用例 b：零退出码，正常返回，不抛异常。
 *  - 用例 c：sleep 5 + timeoutSeconds=1，触发超时路径，异常消息含 "命令超时(1s)"。
 *
 * 未覆盖：
 *  - join 预算耗尽守卫路径（"可能不完整" 标注）为防御性语义。该路径要求进程退出后
 *    管道中仍有 >2000ms 才读得完的数据，而 BufferedReader 消费极快，无法在单测中
 *    确定性触发，故不覆盖。
 */
class FfmpegOutputRaceV232Test {

    /** 反射获取 FfmpegService.run(List<String>, long) —— 精确匹配签名，避免模糊匹配误命中。 */
    private static Method findRunMethod() throws NoSuchMethodException {
        Method m = FfmpegService.class.getDeclaredMethod("run", List.class, long.class);
        m.setAccessible(true);
        return m;
    }

    /** 调用 run，返回异常消息；若未抛异常则返回 null。 */
    private static String invokeRunForMessage(FfmpegService svc, List<String> cmd, long timeoutSeconds) throws Exception {
        Method run = findRunMethod();
        try {
            run.invoke(svc, cmd, timeoutSeconds);
            return null;
        } catch (java.lang.reflect.InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause == null) {
                throw e;
            }
            return cause.getMessage();
        }
    }

    /** 调用 run，断言正常返回。 */
    private static void invokeRunExpectOk(FfmpegService svc, List<String> cmd, long timeoutSeconds) throws Exception {
        Method run = findRunMethod();
        try {
            run.invoke(svc, cmd, timeoutSeconds);
        } catch (java.lang.reflect.InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause instanceof Exception) {
                throw (Exception) cause;
            }
            throw e;
        }
    }

    /**
     * 用例 a：慢速小输出 + 非零退出 → snippet 含尾部标记，且总输出 <500 字符。
     *
     * 诚实声明：这是修复后的行为契约。旧代码在低概率时序下可能丢失尾部输出，
     * 本用例不承诺在旧代码上稳定失败。
     */
    @Test
    void slowSmallOutputNonZeroExit_keepsTailMarker_andStaysSmall() throws Exception {
        FfmpegService svc = new FfmpegService("ffmpeg", "ffprobe");
        // 逐行慢速输出：先输出若干中间行，最后输出尾部标记 TAIL_MARKER_V232，然后 exit 3。
        String script =
                "i=0; while [ $i -lt 5 ]; do echo \"line-$i\"; i=$((i+1)); sleep 0.05; done; " +
                "echo TAIL_MARKER_V232; exit 3";
        List<String> cmd = List.of("sh", "-c", script);

        String msg = invokeRunForMessage(svc, cmd, 30L);

        assertNotNull(msg, "非零退出码应抛出异常并携带消息");
        assertTrue(msg.contains("TAIL_MARKER_V232"),
                "snippet 应包含尾部标记 TAIL_MARKER_V232，实际消息=" + msg);
        assertTrue(msg.length() < 500,
                "总输出应小于 500 字符，实际长度=" + msg.length() + "，消息=" + msg);
    }

    /** 用例 b：零退出码 → 无异常。 */
    @Test
    void zeroExit_doesNotThrow() throws Exception {
        FfmpegService svc = new FfmpegService("ffmpeg", "ffprobe");
        List<String> cmd = List.of("sh", "-c", "echo hello; exit 0");
        invokeRunExpectOk(svc, cmd, 30L);
    }

    /** 用例 c：sleep 5 + timeoutSeconds=1 → 超时异常，消息含 "命令超时(1s)"。 */
    @Test
    void timeout_reportsConfiguredSeconds() throws Exception {
        FfmpegService svc = new FfmpegService("ffmpeg", "ffprobe");
        List<String> cmd = List.of("sh", "-c", "sleep 5");

        String msg = invokeRunForMessage(svc, cmd, 1L);

        assertNotNull(msg, "超时路径应抛出异常并携带消息");
        assertTrue(msg.contains("命令超时(1s)"),
                "超时消息应包含 \"命令超时(1s)\"，实际消息=" + msg);
    }
}
