package com.dramafactory.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/**
 * ffmpeg 流水线封装服务。
 * <p>
 * 提供生成测试片段、拼接片段、烧录字幕、探测时长等常用能力，
 * 所有外部进程调用均通过统一的 {@link #run(List, long)} 方法执行，
 * 保证超时控制与错误信息的可读性。
 * <p>
 * 失败分类：{@link FfmpegException} 携带 {@code transientFailure} 标记，
 * 用于区分可重试的瞬时故障（如超时、非零退出码、IO 中断等）与
 * 不可重试的永久故障（如命令无法启动、参数非法、输出路径缺少父目录等）。
 * 调用方可据此决定是否执行有界重试。
 */
@Service
public class FfmpegService {

    private static final Logger log = LoggerFactory.getLogger(FfmpegService.class);

    /** ffmpeg 可执行文件路径或命令名。 */
    private final String ffmpeg;

    /** ffprobe 可执行文件路径或命令名。 */
    private final String ffprobe;

    /**
     * 构造器注入 ffmpeg / ffprobe 配置。
     *
     * @param ffmpeg  ffmpeg 命令
     * @param ffprobe ffprobe 命令
     */
    public FfmpegService(@Value("${drama.ffmpeg:ffmpeg}") String ffmpeg,
                         @Value("${drama.ffprobe:ffprobe}") String ffprobe) {
        this.ffmpeg = ffmpeg;
        this.ffprobe = ffprobe;
    }

    /**
     * ffmpeg 可执行文件路径或命令名（供需要直接拼装命令的调用方使用）。
     */
    public String getFfmpeg() {
        return ffmpeg;
    }


    /**
     * ffmpeg 执行异常，包装超时、非零退出码等错误。
     * <p>
     * 分类语义：{@code transientFailure} 为 {@code true} 表示瞬时故障，
     * 通常由外部环境波动（超时、进程被中断、非零退出码、IO 失败等）引起，
     * 可通过有界重试恢复；为 {@code false} 表示永久故障，
     * 例如命令无法启动（二进制缺失/权限不足时永久，见 isTransientLaunchFailure；EAGAIN/ENOMEM/EMFILE 类瞬时资源异常除外）、参数非法、输出路径缺少父目录等，重试不会成功。
     * <p>
     * 兼容构造器（未显式传入分类）默认使用保守值 {@code true}：
     * 即便分类不确定，也可交由有界重试来覆盖，不会造成无限重试。
     */
    public static class FfmpegException extends RuntimeException {

        /** 是否为瞬时（可重试）故障。 */
        private final boolean transientFailure;

        /**
         * 兼容构造器：默认按瞬时故障处理（保守默认，有界重试可覆盖）。
         */
        public FfmpegException(String m) {
            this(m, true);
        }

        /**
         * 兼容构造器：默认按瞬时故障处理（保守默认，有界重试可覆盖）。
         */
        public FfmpegException(String m, Throwable t) {
            this(m, t, true);
        }

        public FfmpegException(String m, boolean transientFailure) {
            super(m);
            this.transientFailure = transientFailure;
        }

        public FfmpegException(String m, Throwable t, boolean transientFailure) {
            super(m, t);
            this.transientFailure = transientFailure;
        }

        public boolean isTransient() {
            return transientFailure;
        }
    }

    /**
     * v2.32 引入（flaky-4）：专用中断异常，承载"线程被中断"信号。
     * <p>
     * 语义约定：中断必须走终止路径，不许进入重试 / 重排。与普通
     * {@link FfmpegException}({@code transient=true}) 的区别在于：
     * 普通瞬时异常表示"外部环境波动，可通过有界重试恢复"；本类型表示
     * "调用线程被中断，上层必须立即停止"，不应被 {@code isTransient}
     * 判定为可重试，也不应进入退避睡眠。
     * <p>
     * 双保险：构造器固定传入 {@code super(m, t, false)}，即 {@code isTransient()}
     * 恒为 {@code false}；即使某处漏判专用类型而落入 {@code catch (FfmpegException)}，
     * 也不会被当作 transient 重试。
     */
    public static class FfmpegInterruptedException extends FfmpegException {

        /**
         * 构造中断异常。
         *
         * @param m 消息
         * @param t 根因（应为 {@link InterruptedException}）
         */
        public FfmpegInterruptedException(String m, Throwable t) {
            super(m, t, false);
        }
    }

    /**
     * v2.31：对 ProcessBuilder.start() 抛出的 IOException 做瞬时/永久分类。
     * <p>
     * 瞬时（true）：消息中出现资源耗尽信号——cannot allocate memory（ENOMEM）、
     * too many open files（EMFILE）、resource temporarily unavailable（EAGAIN），
     * 这类失败重试可能成功。
     * <p>
     * 永久（false）：no such file or directory（error=2，二进制缺失）、permission denied /
     * access is denied（权限不足），以及无法识别的其它消息（保持 v2.29 既有行为：启动失败默认永久）。
     */
    static boolean isTransientLaunchFailure(IOException e) {
        String msg = e.getMessage();
        String lower = msg == null ? "" : msg.toLowerCase(Locale.ROOT);
        if (lower.contains("cannot allocate memory")
                || lower.contains("too many open files")
                || lower.contains("resource temporarily unavailable")) {
            return true;
        }
        return false;
    }

    /**
     * 执行外部命令，统一处理超时与错误输出。
     *
     * @param cmd            命令及参数列表
     * @param timeoutSeconds 超时秒数
     */
    private void run(List<String> cmd, long timeoutSeconds) {
        ProcessBuilder pb = new ProcessBuilder(cmd);
        // 合并标准错误流到标准输出，便于统一收集
        pb.redirectErrorStream(true);

        Process process;
        try {
            process = pb.start();
        } catch (IOException e) {
            throw new FfmpegException("无法启动命令: " + String.join(" ", cmd), e, isTransientLaunchFailure(e));
        }

        StringBuilder output = new StringBuilder();
        // 在独立线程中读取输出，避免管道缓冲区写满导致进程阻塞
        Thread reader = new Thread(() -> {
            try (BufferedReader br = new BufferedReader(
                    new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) {
                    output.append(line).append('\n');
                }
            } catch (IOException e) {
                log.warn("读取 ffmpeg 输出失败: {}", e.getMessage());
            }
        }, "ffmpeg-output-reader");
        reader.setDaemon(true);
        reader.start();

        long startNanos = System.nanoTime();

        boolean finished;
        try {
            finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw new FfmpegInterruptedException("等待命令时被中断: " + String.join(" ", cmd), e);
        }

        long elapsedMillis = (System.nanoTime() - startNanos) / 1_000_000L;
        if (elapsedMillis > 30_000L) {
            String cmdText = String.join(" ", cmd);
            String[] words = cmdText.split(" ");
            String firstTwo = words.length >= 2 ? words[0] + " " + words[1] : cmdText;
            log.warn("ffmpeg 命令执行耗时 {} 秒（前两个命令词: {}）",
                    elapsedMillis / 1000.0, firstTwo);
        }

        if (!finished) {
            process.destroyForcibly();
            throw new FfmpegException("命令超时(" + timeoutSeconds + "s): " + String.join(" ", cmd), true);
        }

        // v2.32：保留有上限的等待（复用 2000ms 预算），并循环 join 直到 reader 结束或预算耗尽；
        // 目的是在读取 output 前尽量确立 reader 已终止，同时不引入挂死风险（进程已退出，写端已关，reader 终将 EOF）。
        // 若预算耗尽而 reader 仍 alive，则用 reader.isAlive() 守卫，不把 output 当完整内容使用。
        long joinDeadlineNanos = System.nanoTime() + 2_000_000_000L;
        boolean readerFinished;
        while (true) {
            long remainingNanos = joinDeadlineNanos - System.nanoTime();
            if (remainingNanos <= 0L) {
                readerFinished = !reader.isAlive();
                break;
            }
            try {
                reader.join(TimeUnit.NANOSECONDS.toMillis(remainingNanos) + 1L);
            } catch (InterruptedException e) {
                // v2.32：红线 7 要求——保留中断标志的恢复；中断后不读可能不完整的 output，
                // 直接抛不带 snippet 的 FfmpegInterruptedException，避免把不完整内容伪装成完整 snippet。
                // v2.32 flaky-4：B2 已把此点改为"恢复标志后走传播路径"，按 B3 划分原则归属第 4 条，本批一并收敛为专用中断异常。
                Thread.currentThread().interrupt();
                throw new FfmpegInterruptedException("等待命令输出读取线程时被中断（输出可能不完整）: "
                        + String.join(" ", cmd), e);
            }
            if (!reader.isAlive()) {
                readerFinished = true;
                break;
            }
        }

        int exitCode = process.exitValue();
        if (exitCode != 0) {
            // v2.32：reader.isAlive() 守卫——只有确认 reader 已结束才把 output 当完整内容读取；
            // 否则明确标注 snippet 可能不完整，绝不伪装成完整 snippet。
            String out = readerFinished ? output.toString() : "";
            String snippet;
            String incompletenessNote;
            if (readerFinished) {
                snippet = out.length() > 500 ? out.substring(0, 500) : out;
                incompletenessNote = "";
            } else {
                incompletenessNote = "（注意：输出读取线程未在等待上限内结束，snippet 可能不完整）";
                snippet = "";
            }
            throw new FfmpegException("命令执行失败(退出码 " + exitCode + "): "
                    + String.join(" ", cmd) + "\n输出" + incompletenessNote + ": " + snippet, true);
        }
    }

    /**
     * 生成测试片段（使用 lavfi testsrc 源）。
     *
     * @param out     输出文件路径
     * @param seconds 时长（秒）
     */
    public void generateTestClip(Path out, int seconds) {
        try {
            Path parent = out.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
        } catch (IOException e) {
            throw new FfmpegException("无法创建输出目录: " + out, e, true);
        }

        List<String> cmd = new ArrayList<>();
        cmd.add(ffmpeg);
        cmd.add("-y");
        cmd.add("-f");
        cmd.add("lavfi");
        cmd.add("-i");
        cmd.add("testsrc=duration=" + seconds + ":size=1280x720:rate=24");
        cmd.add("-c:v");
        cmd.add("libx264");
        cmd.add("-pix_fmt");
        cmd.add("yuv420p");
        cmd.add("-t");
        cmd.add(String.valueOf(seconds));
        cmd.add(out.toString());

        run(cmd, 120);
    }

    /**
     * 拼接多个视频片段为单个输出文件。
     *
     * @param inputs 输入片段列表（非空）
     * @param output 输出文件
     */
    public void concatClips(List<Path> inputs, Path output) {
        if (inputs == null || inputs.isEmpty()) {
            throw new FfmpegException("拼接片段列表不能为空", false);
        }

        Path parent = output.getParent();
        if (parent == null) {
            throw new FfmpegException("输出文件缺少父目录: " + output, false);
        }

        try {
            Files.createDirectories(parent);
        } catch (IOException e) {
            throw new FfmpegException("无法创建输出目录: " + parent, e, true);
        }

        Path listFile = parent.resolve("concat_list.txt");
        StringBuilder sb = new StringBuilder();
        for (Path in : inputs) {
            // 单引号在 concat 列表中需要转义为 '\''
            String absolute = in.toAbsolutePath().toString().replace("'", "'\\''");
            sb.append("file '").append(absolute).append("'\n");
        }

        try {
            Files.writeString(listFile, sb.toString(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new FfmpegException("写入 concat 列表失败: " + listFile, e, true);
        }

        List<String> cmd = new ArrayList<>();
        cmd.add(ffmpeg);
        cmd.add("-y");
        cmd.add("-f");
        cmd.add("concat");
        cmd.add("-safe");
        cmd.add("0");
        cmd.add("-i");
        cmd.add(listFile.toString());
        cmd.add("-c:v");
        cmd.add("libx264");
        cmd.add("-pix_fmt");
        cmd.add("yuv420p");
        cmd.add(output.toString());

        run(cmd, 600);
    }

    /**
     * 为视频烧录字幕。
     * <p>
     * 由于 subtitles 滤镜对路径转义较为敏感，这里将 srt 复制为输出目录下的
     * ASCII 文件名 subs.srt，再进行烧录。
     *
     * @param input  输入视频
     * @param srt    字幕文件
     * @param output 输出视频
     */
    /**
     * 转义 subtitles 滤镜的文件路径：反斜杠、冒号、单引号需加反斜杠转义。
     */
    static String escapeSubtitlesPath(String path) {
        return "'" + path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'") + "'";
    }

    public void burnSubtitles(Path input, Path srt, Path output) {
        Path parent = output.getParent();
        if (parent == null) {
            throw new FfmpegException("输出文件缺少父目录: " + output, false);
        }

        try {
            Files.createDirectories(parent);
        } catch (IOException e) {
            throw new FfmpegException("无法创建输出目录: " + parent, e, true);
        }

        Path asciiSrt = parent.resolve("subs.srt");
        try {
            Files.copy(srt, asciiSrt, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            throw new FfmpegException("复制字幕文件失败: " + srt + " -> " + asciiSrt, e, true);
        }

        // subtitles 滤镜的文件名走滤镜选项解析，需用绝对路径并转义特殊字符（: ' \）
        String subPath = escapeSubtitlesPath(asciiSrt.toAbsolutePath().toString());
        List<String> cmd = new ArrayList<>();
        cmd.add(ffmpeg);
        cmd.add("-y");
        cmd.add("-i");
        cmd.add(input.toString());
        cmd.add("-vf");
        cmd.add("subtitles=" + subPath);
        cmd.add("-c:a");
        cmd.add("copy");
        cmd.add(output.toString());

        run(cmd, 600);
    }

    /**
     * 使用 ffprobe 探测媒体文件的时长（秒）。
     *
     * @param file 媒体文件
     * @return 时长（秒），无法解析时抛异常
     */
    public double probeDurationSeconds(Path file) {
        List<String> cmd = new ArrayList<>();
        cmd.add(ffprobe);
        cmd.add("-v");
        cmd.add("error");
        cmd.add("-show_entries");
        cmd.add("format=duration");
        cmd.add("-of");
        cmd.add("csv=p=0");
        cmd.add(file.toString());

        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.redirectErrorStream(true);

        Process process;
        try {
            process = pb.start();
        } catch (IOException e) {
            throw new FfmpegException("无法启动 ffprobe: " + String.join(" ", cmd), e, false);
        }

        StringBuilder output = new StringBuilder();
        try (BufferedReader br = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = br.readLine()) != null) {
                output.append(line).append('\n');
            }
        } catch (IOException e) {
            throw new FfmpegException("读取 ffprobe 输出失败: " + file, e, true);
        }

        try {
            boolean finished = process.waitFor(60, TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                throw new FfmpegException("ffprobe 超时: " + file, true);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw new FfmpegInterruptedException("等待 ffprobe 时被中断: " + file, e);
        }

        if (process.exitValue() != 0) {
            String out = output.toString();
            String snippet = out.length() > 500 ? out.substring(0, 500) : out;
            throw new FfmpegException("ffprobe 执行失败: " + file + "\n输出: " + snippet, true);
        }

        String raw = output.toString().trim();
        if (raw.isEmpty()) {
            throw new FfmpegException("ffprobe 未返回时长信息: " + file, true);
        }

        // 可能包含多行，取第一行有效数字
        String firstLine = raw.split("\\R", 2)[0].trim();
        try {
            return Double.parseDouble(firstLine);
        } catch (NumberFormatException e) {
            throw new FfmpegException("无法解析时长: " + firstLine, e, true);
        }
    }

    /**
     * 从视频中抽取成片海报帧。
     * <p>使用 ffmpeg 从视频第 1 秒处抽取一帧，输出为 JPEG 图片。
     * 命令格式：{@code -ss 1 -i <video> -vframes 1 -q:v 3 <posterJpg>}，
     * 超时时间为 60 秒，失败时抛出 {@link FfmpegException}。</p>
     *
     * @param video     输入视频文件路径
     * @param posterJpg 输出海报图片（JPEG）路径
     * @throws FfmpegException 当 ffmpeg 抽取失败或超时时抛出
     */
    public void extractPoster(Path video, Path posterJpg) {
        List<String> cmd = List.of(
                ffmpeg,
                "-y",
                "-ss", "1",
                "-i", video.toString(),
                "-vframes", "1",
                "-q:v", "3",
                posterJpg.toString()
        );
        run(cmd, 60);
    }

    /**
     * 转换视频格式 / 压缩分辨率。
     * <p>mp4 走 libx264+aac；webm 走 libvpx-vp9+libopus；maxWidth 非空时按比例缩放到该宽度。</p>
     *
     * @param input    输入视频
     * @param output   输出视频
     * @param format   目标格式：mp4 或 webm（其他值按 mp4 处理）
     * @param maxWidth 目标宽度像素，可空
     */
    public void convertVideo(Path input, Path output, String format, Integer maxWidth) {
        List<String> cmd = new ArrayList<>();
        cmd.add(ffmpeg);
        cmd.add("-y");
        cmd.add("-i");
        cmd.add(input.toString());
        if (maxWidth != null) {
            cmd.add("-vf");
            cmd.add("scale=" + maxWidth + ":-2");
        }
        if ("webm".equalsIgnoreCase(format)) {
            cmd.add("-c:v");
            cmd.add("libvpx-vp9");
            cmd.add("-b:v");
            cmd.add("0");
            cmd.add("-crf");
            cmd.add("30");
            cmd.add("-c:a");
            cmd.add("libopus");
        } else {
            cmd.add("-c:v");
            cmd.add("libx264");
            cmd.add("-pix_fmt");
            cmd.add("yuv420p");
            cmd.add("-c:a");
            cmd.add("aac");
        }
        cmd.add(output.toString());
        run(cmd, 600);
    }

    /**
     * 从视频提取音频。
     * <p>mp3 走 libmp3lame；wav 走 pcm_s16le。</p>
     *
     * @param input  输入视频
     * @param output 输出音频
     * @param format 目标格式：mp3 或 wav（其他值按 mp3 处理）
     */
    public void extractAudio(Path input, Path output, String format) {
        List<String> cmd = new ArrayList<>();
        cmd.add(ffmpeg);
        cmd.add("-y");
        cmd.add("-i");
        cmd.add(input.toString());
        cmd.add("-vn");
        if ("wav".equalsIgnoreCase(format)) {
            cmd.add("-c:a");
            cmd.add("pcm_s16le");
        } else {
            cmd.add("-c:a");
            cmd.add("libmp3lame");
            cmd.add("-q:a");
            cmd.add("4");
        }
        cmd.add(output.toString());
        run(cmd, 600);
    }
}
