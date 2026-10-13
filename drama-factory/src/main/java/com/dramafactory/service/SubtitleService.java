package com.dramafactory.service;

import com.dramafactory.model.Shot;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

/**
 * 字幕服务：根据分镜对白生成 SRT 字幕文件。
 */
@Service
public class SubtitleService {

    /** 每个分镜默认时长（秒），durationSeconds 为空时使用 */
    private static final int DEFAULT_DURATION_SECONDS = 5;

    /** 单行字幕文本最大字符数，超出则换行 */
    private static final int MAX_LINE_LENGTH = 40;

    private final String storageDir;

    /**
     * 构造器注入存储根目录。
     *
     * @param storageDir 存储根目录，来自配置 drama.storage
     */
    public SubtitleService(@Value("${drama.storage:./data/media}") String storageDir) {
        this.storageDir = storageDir;
    }

    /**
     * 根据分镜列表生成 SRT 字幕文件。
     * <p>
     * 时间轴从 00:00:00,000 开始，每个分镜占据 durationSeconds 秒（为空按 5 秒）。
     * 文本取分镜对白，对白为空则取描述，再为空则跳过该条字幕，但时间轴仍推进，
     * 以保证字幕与视频画面时间对齐。
     *
     * @param episodeId 剧集 ID
     * @param shots     已按 shotNo 升序排列的分镜列表
     * @return 生成的 SRT 文件路径
     */
    public Path buildSrt(Long episodeId, List<Shot> shots) {
        // 起始时间轴（毫秒）
        long cursorMillis = 0L;
        // 字幕序号
        int index = 1;
        StringBuilder builder = new StringBuilder();

        for (Shot shot : shots) {
            // 计算当前分镜时长（秒）
            int durationSeconds = shot.getDurationSeconds() == null
                    ? DEFAULT_DURATION_SECONDS
                    : shot.getDurationSeconds();
            if (durationSeconds < 0) {
                durationSeconds = 0;
            }
            long durationMillis = durationSeconds * 1000L;
            long startMillis = cursorMillis;
            long endMillis = cursorMillis + durationMillis;
            // 时间轴推进，保持与视频对齐
            cursorMillis = endMillis;

            // 取字幕文本：优先对白，其次描述
            String text = shot.getDialogue();
            if (text == null || text.isBlank()) {
                text = shot.getDescription();
            }
            // 文本为空则跳过该条字幕（时间轴已推进）
            if (text == null || text.isBlank()) {
                continue;
            }

            builder.append(index).append("\r\n");
            builder.append(formatTime(startMillis)).append(" --> ").append(formatTime(endMillis)).append("\r\n");
            builder.append(wrapText(text.trim())).append("\r\n");
            builder.append("\r\n");
            index++;
        }

        // 输出目录：storageDir/subs
        Path subsDir = Paths.get(storageDir, "subs");
        Path targetFile = subsDir.resolve("episode_" + episodeId + ".srt");
        try {
            Files.createDirectories(subsDir);
            Files.writeString(targetFile, builder.toString(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException("写入字幕文件失败: " + targetFile, e);
        }
        return targetFile;
    }

    /**
     * 将毫秒时间戳格式化为 SRT 时间：HH:MM:SS,mmm。
     *
     * @param millis 毫秒时间戳
     * @return 格式化后的时间字符串
     */
    private String formatTime(long millis) {
        long totalSeconds = millis / 1000L;
        long ms = millis % 1000L;
        long h = totalSeconds / 3600L;
        long m = (totalSeconds % 3600L) / 60L;
        long s = totalSeconds % 60L;
        return String.format("%02d:%02d:%02d,%03d", h, m, s, ms);
    }

    /**
     * 文本过长时按最大长度简单切分换行。
     *
     * @param text 原始文本
     * @return 换行后的文本
     */
    private String wrapText(String text) {
        if (text.length() <= MAX_LINE_LENGTH) {
            return text;
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < text.length(); i += MAX_LINE_LENGTH) {
            if (i > 0) {
                sb.append("\r\n");
            }
            int end = Math.min(i + MAX_LINE_LENGTH, text.length());
            sb.append(text, i, end);
        }
        return sb.toString();
    }
}
