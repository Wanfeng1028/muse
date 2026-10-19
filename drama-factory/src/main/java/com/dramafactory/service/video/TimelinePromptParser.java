package com.dramafactory.service.video;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * H3-Continuum 风格的时间线提示词解析器。
 *
 * <p>支持的格式（参考 ComfyUI-H3-Continuum v2/prompts.py）：
 * <pre>
 * 前言文本（可选，作用于所有分段）
 *
 * [0-10s]
 * @R1 穿过安静的走廊，镜头跟随
 *
 * [10-20s]
 * @R2 从右边入场，镜头转向 @R2
 * </pre>
 *
 * <p>规则：
 * <ul>
 *   <li>时间头：{@code [0-10s]}、{@code [0s-10sec]}、{@code [Chunk 1]} 三种写法，大小写不敏感</li>
 *   <li>参考标记：{@code @R1} ~ {@code @R9}，从每段正文中提取</li>
 *   <li>前言（第一个时间头之前的文本）会拼到每段提示词前面</li>
 *   <li>解析是确定性的、无副作用的纯函数</li>
 * </ul>
 */
public class TimelinePromptParser {

    /** 时间头：[0-10s] / [0s - 10sec] 等写法。 */
    private static final Pattern TIMELINE_HEADER = Pattern.compile(
            "^\\s*\\[\\s*(\\d+(?:\\.\\d+)?)\\s*(?:s|sec|seconds)?\\s*[-–—]\\s*(\\d+(?:\\.\\d+)?)\\s*(?:s|sec|seconds)?\\s*\\]\\s*$",
            Pattern.CASE_INSENSITIVE);

    /** 分块头：[Chunk 1] / [Clip 2]。 */
    private static final Pattern CHUNK_HEADER = Pattern.compile(
            "^\\s*\\[\\s*(?:chunk|clip)\\s*(\\d+)\\s*\\]\\s*$",
            Pattern.CASE_INSENSITIVE);

    /** 参考标记：@R1 ~ @R9。 */
    private static final Pattern REF_TAG = Pattern.compile("@R([1-9])");

    /**
     * 解析后的单个时间段。
     *
     * @param index   分段序号（从 1 开始）
     * @param startSec 起始秒
     * @param endSec   结束秒
     * @param prompt   该段提示词（已拼入前言）
     * @param refTags  该段引用的参考标记，如 ["R1", "R2"]
     */
    public record TimelineSection(int index, double startSec, double endSec,
                                  String prompt, List<String> refTags) {
    }

    /**
     * 解析时间线脚本。
     *
     * @param script 时间线脚本文本
     * @param chunks 期望的分段数（用于 [Chunk N] 写法校验）
     * @return 按顺序的时间段列表
     * @throws IllegalArgumentException 脚本格式非法时
     */
    public static List<TimelineSection> parse(String script, int chunks) {
        if (script == null || script.isBlank()) {
            throw new IllegalArgumentException("时间线脚本不能为空");
        }
        if (chunks < 1) {
            throw new IllegalArgumentException("分段数必须 >= 1");
        }

        List<RawSection> raw = splitSections(script);
        if (raw.isEmpty()) {
            throw new IllegalArgumentException("时间线脚本不包含任何 [0-10s] 或 [Chunk N] 分段头");
        }

        String preamble = extractPreamble(script);
        List<TimelineSection> result = new ArrayList<>();
        int index = 1;
        for (RawSection section : raw) {
            String prompt = section.body().strip();
            if (prompt.isEmpty()) {
                throw new IllegalArgumentException(
                        "分段 " + section.headerSource() + " 的正文为空，请在时间头下方填写提示词");
            }
            String fullPrompt = preamble.isEmpty() ? prompt : preamble + "\n\n" + prompt;
            List<String> refTags = extractRefTags(prompt);
            result.add(new TimelineSection(index++, section.startSec(), section.endSec(),
                    fullPrompt, refTags));
        }
        return Collections.unmodifiableList(result);
    }

    /**
     * 快捷解析：分段数按脚本中实际分段头数量推断。
     */
    public static List<TimelineSection> parse(String script) {
        if (script == null || script.isBlank()) {
            throw new IllegalArgumentException("时间线脚本不能为空");
        }
        int count = countHeaders(script);
        return parse(script, Math.max(1, count));
    }

    /** 提取所有 @R1~@R9 标记（去重、保序）。 */
    public static List<String> extractRefTags(String prompt) {
        if (prompt == null) {
            return List.of();
        }
        List<String> tags = new ArrayList<>();
        Matcher m = REF_TAG.matcher(prompt);
        while (m.find()) {
            String tag = "R" + m.group(1);
            if (!tags.contains(tag)) {
                tags.add(tag);
            }
        }
        return Collections.unmodifiableList(tags);
    }

    /** 是否包含时间线分段头。 */
    public static boolean hasTimelineHeader(String script) {
        if (script == null) {
            return false;
        }
        for (String line : script.split("\n")) {
            if (TIMELINE_HEADER.matcher(line).matches() || CHUNK_HEADER.matcher(line).matches()) {
                return true;
            }
        }
        return false;
    }

    // ---------- 内部实现 ----------

    private record RawSection(double startSec, double endSec, String body, String headerSource) {
    }

    private static List<RawSection> splitSections(String script) {
        List<RawSection> sections = new ArrayList<>();
        String[] lines = script.split("\n");
        String currentHeader = null;
        double currentStart = 0;
        double currentEnd = 0;
        StringBuilder body = new StringBuilder();
        boolean inSection = false;

        for (String line : lines) {
            Matcher timeMatcher = TIMELINE_HEADER.matcher(line);
            Matcher chunkMatcher = CHUNK_HEADER.matcher(line);
            if (timeMatcher.matches() || chunkMatcher.matches()) {
                if (inSection) {
                    sections.add(new RawSection(currentStart, currentEnd,
                            body.toString(), currentHeader));
                }
                if (timeMatcher.matches()) {
                    currentStart = Double.parseDouble(timeMatcher.group(1));
                    currentEnd = Double.parseDouble(timeMatcher.group(2));
                    if (!(currentEnd > currentStart)) {
                        throw new IllegalArgumentException(
                                "时间头 " + line.strip() + " 非法：结束时间必须大于起始时间");
                    }
                } else {
                    int chunkIndex = Integer.parseInt(chunkMatcher.group(1));
                    if (chunkIndex < 1) {
                        throw new IllegalArgumentException(
                                "分块序号必须从 1 开始：" + line.strip());
                    }
                    // [Chunk N] 写法：序号映射为占位时间轴，调用方按顺序使用
                    currentStart = chunkIndex - 1;
                    currentEnd = chunkIndex;
                }
                currentHeader = line.strip();
                body = new StringBuilder();
                inSection = true;
            } else if (inSection) {
                body.append(line).append("\n");
            }
        }
        if (inSection) {
            sections.add(new RawSection(currentStart, currentEnd, body.toString(), currentHeader));
        }
        return sections;
    }

    private static String extractPreamble(String script) {
        StringBuilder sb = new StringBuilder();
        for (String line : script.split("\n")) {
            if (TIMELINE_HEADER.matcher(line).matches() || CHUNK_HEADER.matcher(line).matches()) {
                break;
            }
            sb.append(line).append("\n");
        }
        return sb.toString().strip();
    }

    private static int countHeaders(String script) {
        int count = 0;
        for (String line : script.split("\n")) {
            if (TIMELINE_HEADER.matcher(line).matches() || CHUNK_HEADER.matcher(line).matches()) {
                count++;
            }
        }
        return count;
    }
}
