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
import java.util.concurrent.TimeUnit;

/**
 * ffmpeg 流水线封装服务。
 * <p>
 * 提供生成测试片段、拼接片段、烧录字幕、探测时长等常用能力，
 * 所有外部进程调用均通过统一的 {@link #run(List, long)} 方法执行，
 * 保证超时控制与错误信息的可读性。
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
     */
    public static class FfmpegException extends RuntimeException {
        public FfmpegException(String m) {
            super(m);
        }

        public FfmpegException(String m, Throwable t) {
            super(m, t);
        }
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
            throw new FfmpegException("无法启动命令: " + String.join(" ", cmd), e);
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

        boolean finished;
        try {
            finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw new FfmpegException("等待命令时被中断: " + String.join(" ", cmd), e);
        }

        if (!finished) {
            process.destroyForcibly();
            throw new FfmpegException("命令超时(" + timeoutSeconds + "s): " + String.join(" ", cmd));
        }

        try {
            reader.join(2000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        int exitCode = process.exitValue();
        if (exitCode != 0) {
            String out = output.toString();
            String snippet = out.length() > 500 ? out.substring(0, 500) : out;
            throw new FfmpegException("命令执行失败(退出码 " + exitCode + "): "
                    + String.join(" ", cmd) + "\n输出: " + snippet);
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
            throw new FfmpegException("无法创建输出目录: " + out, e);
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
            throw new FfmpegException("拼接片段列表不能为空");
        }

        Path parent = output.getParent();
        if (parent == null) {
            throw new FfmpegException("输出文件缺少父目录: " + output);
        }

        try {
            Files.createDirectories(parent);
        } catch (IOException e) {
            throw new FfmpegException("无法创建输出目录: " + parent, e);
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
            throw new FfmpegException("写入 concat 列表失败: " + listFile, e);
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
            throw new FfmpegException("输出文件缺少父目录: " + output);
        }

        try {
            Files.createDirectories(parent);
        } catch (IOException e) {
            throw new FfmpegException("无法创建输出目录: " + parent, e);
        }

        Path asciiSrt = parent.resolve("subs.srt");
        try {
            Files.copy(srt, asciiSrt, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            throw new FfmpegException("复制字幕文件失败: " + srt + " -> " + asciiSrt, e);
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
            throw new FfmpegException("无法启动 ffprobe: " + String.join(" ", cmd), e);
        }

        StringBuilder output = new StringBuilder();
        try (BufferedReader br = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = br.readLine()) != null) {
                output.append(line).append('\n');
            }
        } catch (IOException e) {
            throw new FfmpegException("读取 ffprobe 输出失败: " + file, e);
        }

        try {
            boolean finished = process.waitFor(60, TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                throw new FfmpegException("ffprobe 超时: " + file);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw new FfmpegException("等待 ffprobe 时被中断: " + file, e);
        }

        if (process.exitValue() != 0) {
            String out = output.toString();
            String snippet = out.length() > 500 ? out.substring(0, 500) : out;
            throw new FfmpegException("ffprobe 执行失败: " + file + "\n输出: " + snippet);
        }

        String raw = output.toString().trim();
        if (raw.isEmpty()) {
            throw new FfmpegException("ffprobe 未返回时长信息: " + file);
        }

        // 可能包含多行，取第一行有效数字
        String firstLine = raw.split("\\R", 2)[0].trim();
        try {
            return Double.parseDouble(firstLine);
        } catch (NumberFormatException e) {
            throw new FfmpegException("无法解析时长: " + firstLine, e);
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
}
