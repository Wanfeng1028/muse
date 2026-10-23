package com.dramafactory.service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

@Service
public class SubtitleTranscriptService {

    private static final Logger log = LoggerFactory.getLogger(SubtitleTranscriptService.class);

    /* SRT 时间戳格式：00:01:23,456 --> 00:01:25,789 */
    private static final Pattern SRT_TS = Pattern.compile(
            "(\\d{2}:\\d{2}:\\d{2},\\d{3})\\s*-->\\s*(\\d{2}:\\d{2}:\\d{2},\\d{3})");

    /* VTT 时间戳格式：00:01:23.456 --> 00:01:25.789 */
    private static final Pattern VTT_TS = Pattern.compile(
            "(\\d{2}:\\d{2}:\\d{2}\\.\\d{3})\\s*-->\\s*(\\d{2}:\\d{2}:\\d{2}\\.\\d{3})");

    private final FfmpegService ffmpegService;
    private final ObjectMapper objectMapper;

    public SubtitleTranscriptService(FfmpegService ffmpegService, ObjectMapper objectMapper) {
        this.ffmpegService = ffmpegService;
        this.objectMapper = objectMapper;
    }

    public record TranscriptSegment(double startSec, double endSec, String text) {}

    public record TranscriptResult(boolean found, String trackInfo, List<TranscriptSegment> segments) {}

    public TranscriptResult extract(Path video, Path workDir) {
        try {
            /* ffprobe 列字幕流 */
            List<String> probeCmd = List.of(
                    ffmpegService.getFfprobe(),
                    "-v", "error",
                    "-select_streams", "s",
                    "-show_entries", "stream=index,codec_name:stream_tags=language,title",
                    "-of", "json",
                    video.toString());
            String probeOut = ffmpegService.executeCapture(probeCmd, 60);

            JsonNode root = objectMapper.readTree(probeOut);
            JsonNode streams = root.path("streams");

            if (!streams.isArray() || streams.isEmpty()) {
                return new TranscriptResult(false, "无内嵌字幕轨道", List.of());
            }

            /* 选流：优先 language 为 chi/zho/zh 的第一条，否则第一条 */
            int relIdx = -1;
            JsonNode chosen = null;
            for (int i = 0; i < streams.size(); i++) {
                String lang = streams.get(i).path("stream_tags").path("language").asText("");
                if ("chi".equals(lang) || "zho".equals(lang) || "zh".equals(lang)) {
                    chosen = streams.get(i);
                    relIdx = i;
                    break;
                }
            }
            if (chosen == null) {
                chosen = streams.get(0);
                relIdx = 0;
            }

            String codec = chosen.path("codec_name").asText("unknown");
            String lang = chosen.path("stream_tags").path("language").asText("");
            String trackInfo = "s:" + relIdx + " (" + lang + ", " + codec + ")";

            /* 创建工作目录并抽取字幕 */
            Files.createDirectories(workDir);
            List<String> extractCmd = List.of(
                    ffmpegService.getFfmpeg(),
                    "-hide_banner",
                    "-loglevel", "error",
                    "-i", video.toString(),
                    "-map", "0:s:" + relIdx,
                    "-y", workDir.resolve("transcript.srt").toString());
            ffmpegService.executeCapture(extractCmd, 120);

            /* 读取字幕文件 */
            String content = Files.readString(workDir.resolve("transcript.srt"), StandardCharsets.UTF_8);

            /* 根据 WEBVTT 头判断格式 */
            List<TranscriptSegment> segments = content.startsWith("WEBVTT")
                    ? parseVtt(content)
                    : parseSrt(content);

            return new TranscriptResult(true, trackInfo, segments);

        } catch (FfmpegService.FfmpegException | IOException e) {
            log.warn("内嵌字幕提取失败: {}", e.getMessage());
            return new TranscriptResult(false, "提取失败", List.of());
        }
    }

    public static List<TranscriptSegment> parseSrt(String content) {
        List<TranscriptSegment> result = new ArrayList<>();
        /* 兼容 \r\n，统一换行后按空行切块 */
        String norm = content.replace("\r\n", "\n").replace('\r', '\n');
        String[] blocks = norm.split("\\n\\n");

        for (String block : blocks) {
            String trimmed = block.trim();
            if (trimmed.isEmpty()) continue;

            String[] lines = trimmed.split("\\n");
            if (lines.length < 2) continue;

            /* 第 2 行匹配时间戳 */
            Matcher m = SRT_TS.matcher(lines[1].trim());
            if (!m.find()) continue;

            double start = parseTimestamp(m.group(1));
            double end = parseTimestamp(m.group(2));
            if (start < 0 || end < 0) continue;

            /* 正文为其后所有行用 \n 拼接后 trim */
            StringBuilder sb = new StringBuilder();
            for (int i = 2; i < lines.length; i++) {
                if (i > 2) sb.append('\n');
                sb.append(lines[i]);
            }
            result.add(new TranscriptSegment(start, end, sb.toString().trim()));
        }
        return result;
    }

    public static List<TranscriptSegment> parseVtt(String content) {
        List<TranscriptSegment> result = new ArrayList<>();
        String norm = content.replace("\r\n", "\n").replace('\r', '\n');
        String[] lines = norm.split("\\n");

        /* 跳过 WEBVTT 头（到首个空行） */
        int i = 0;
        while (i < lines.length && !lines[i].isBlank()) {
            i++;
        }
        i++; /* 跳过空行本身 */

        /* 逐块解析 */
        List<String> curBlock = new ArrayList<>();
        boolean inNote = false;

        for (; i < lines.length; i++) {
            String line = lines[i];

            /* NOTE 块：跳过直到空行 */
            if (inNote) {
                if (line.isBlank()) inNote = false;
                continue;
            }
            if (line.trim().startsWith("NOTE")) {
                inNote = true;
                curBlock.clear();
                continue;
            }

            if (line.isBlank()) {
                if (!curBlock.isEmpty()) {
                    parseVttCue(curBlock, result);
                    curBlock.clear();
                }
                continue;
            }
            curBlock.add(line);
        }

        /* 处理末尾块 */
        if (!curBlock.isEmpty()) {
            parseVttCue(curBlock, result);
        }
        return result;
    }

    /* 解析单个 VTT cue 块 */
    private static void parseVttCue(List<String> lines, List<TranscriptSegment> result) {
        for (int i = 0; i < lines.size(); i++) {
            Matcher m = VTT_TS.matcher(lines.get(i).trim());
            if (m.find()) {
                double start = parseTimestamp(m.group(1));
                double end = parseTimestamp(m.group(2));
                if (start < 0 || end < 0) return;

                StringBuilder sb = new StringBuilder();
                for (int j = i + 1; j < lines.size(); j++) {
                    if (sb.length() > 0) sb.append('\n');
                    sb.append(lines.get(j));
                }
                result.add(new TranscriptSegment(start, end, sb.toString().trim()));
                return;
            }
        }
    }

    /* 解析时间戳，失败返回 -1 */
    private static double parseTimestamp(String ts) {
        try {
            /* 兼容 SRT 逗号与 VTT 点分隔 */
            String s = ts.trim().replace(',', '.');
            String[] parts = s.split(":");
            if (parts.length != 3) return -1;
            int hh = Integer.parseInt(parts[0]);
            int mm = Integer.parseInt(parts[1]);
            String[] sec = parts[2].split("\\.");
            if (sec.length != 2) return -1;
            int ss = Integer.parseInt(sec[0]);
            int ms = Integer.parseInt(sec[1]);
            return hh * 3600.0 + mm * 60.0 + ss + ms / 1000.0;
        } catch (NumberFormatException e) {
            return -1;
        }
    }
}