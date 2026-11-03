package com.dramafactory.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.regex.Pattern;

/**
 * Run 步骤日志服务。
 * 负责把每个 step 的日志以追加方式写入 data/logs/run-{runId}/step-{seqNo}.log，
 * 并支持按字节偏移读取，供前端做增量拉取。
 * 安全：runId / seqNo 只接受纯数字，防止路径穿越。
 */
@Service
public class RunLogService {

    private static final Logger log = LoggerFactory.getLogger(RunLogService.class);

    private static final Pattern DIGITS = Pattern.compile("\\d+");
    private static final DateTimeFormatter TS = DateTimeFormatter.ofPattern("HH:mm:ss");
    private static final int DEFAULT_READ_LIMIT = 64 * 1024;

    private final Path baseDir;

    public RunLogService(@Value("${drama.logs.dir:data/logs}") String logsDir) {
        this.baseDir = Paths.get(logsDir).toAbsolutePath().normalize();
    }

    /**
     * 追加一行日志。目录与文件不存在时自动创建，UTF-8 编码，行前加 HH:mm:ss 时间戳。
     */
    public void append(Long runId, Integer seqNo, String line) {
        Path file = resolveFile(runId, seqNo);
        String ts = LocalTime.now().format(TS);
        String content = "[" + ts + "] " + (line == null ? "" : line) + System.lineSeparator();
        try {
            Files.createDirectories(file.getParent());
            Files.writeString(file, content, StandardCharsets.UTF_8,
                    java.nio.file.StandardOpenOption.CREATE,
                    java.nio.file.StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new IllegalStateException("写入 Run 日志失败: " + file, e);
        }
    }

    /**
     * 从 offsetBytes 起读取日志。
     *
     * @param offsetBytes 起始字节偏移，负数按 0 处理
     * @return 读取结果（content / nextOffset / eof）
     */
    public LogReadResult read(Long runId, Integer seqNo, long offsetBytes) {
        Path file = resolveFile(runId, seqNo);
        long start = Math.max(0L, offsetBytes);
        if (!Files.exists(file)) {
            return new LogReadResult("", start, true);
        }
        try (RandomAccessFile raf = new RandomAccessFile(file.toFile(), "r")) {
            long length = raf.length();
            if (start >= length) {
                return new LogReadResult("", length, true);
            }
            raf.seek(start);
            int toRead = (int) Math.min(DEFAULT_READ_LIMIT, length - start);
            byte[] buf = new byte[toRead];
            int read = raf.read(buf, 0, toRead);
            if (read <= 0) {
                return new LogReadResult("", start, start >= length);
            }
            String content = new String(buf, 0, read, StandardCharsets.UTF_8);
            long next = start + read;
            boolean eof = next >= length;
            return new LogReadResult(content, next, eof);
        } catch (IOException e) {
            throw new IllegalStateException("读取 Run 日志失败: " + file, e);
        }
    }

    /**
     * 校验并解析日志文件路径，阻止路径穿越。
     */
    private Path resolveFile(Long runId, Integer seqNo) {
        if (runId == null || seqNo == null) {
            throw new IllegalArgumentException("runId 与 seqNo 不能为空");
        }
        String runIdStr = String.valueOf(runId);
        String seqStr = String.valueOf(seqNo);
        if (!DIGITS.matcher(runIdStr).matches() || !DIGITS.matcher(seqStr).matches()) {
            throw new IllegalArgumentException("runId 与 seqNo 必须为纯数字");
        }
        Path dir = baseDir.resolve("run-" + runIdStr).normalize();
        Path file = dir.resolve("step-" + seqStr + ".log").normalize();
        if (!file.startsWith(baseDir)) {
            throw new IllegalArgumentException("非法日志路径");
        }
        return file;
    }

    /**
     * 日志读取结果。
     *
     * @param content    本次读取到的内容
     * @param nextOffset 下次读取应使用的字节偏移
     * @param eof        是否已到文件末尾
     */
    public record LogReadResult(String content, long nextOffset, boolean eof) {
    }
}
