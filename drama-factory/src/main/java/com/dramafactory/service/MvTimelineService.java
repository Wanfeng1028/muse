package com.dramafactory.service;

import java.util.ArrayList;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.stereotype.Service;

/**
 * AI MV 的"歌词-画面时间轴对齐"纯函数工具类。
 *
 * <p>算法：
 * <ol>
 *   <li>逐段解析 lyrics，按 {@code \n} 切分，每行 trim，丢弃空行；某段切完 0 行抛
 *       {@link IllegalArgumentException}("作词结果含空段落")；sections 缺失/非数组/空数组抛
 *       {@link IllegalArgumentException}("作词结果为空")。</li>
 *   <li>行权重 = 该行 trim 后文本的 Unicode code point 总数，最小计 1；段权重 = 该段所有行权重之和。</li>
 *   <li>段基准 = estSeconds * 1000（先转 long）；行基准 = 段基准 * 行权重 / 段权重（double）。</li>
 *   <li>totalEst = Σ段基准（long）；scale = audioDurationMs &gt; 0 ? (double) audioDurationMs / totalEst : 1.0；
 *       totalMs = audioDurationMs &gt; 0 ? audioDurationMs : totalEst。</li>
 *   <li>行时长 = 行基准 * scale。<b>钳制语义</b>：{@link #MIN_LINE_MS} = 800，第一轮将时长 &lt; 800 的行记为 800；
 *       若钳制后总和超过 totalMs，则对全部行再做一次等比缩放使总和精确等于 totalMs（第二轮不再钳制）。</li>
 *   <li>时间累加：cursor 从 0 开始；每行 startMs = round(cursor)，endMs = round(cursor + 行时长)；cursor = endMs；
 *       最后一行的 endMs 强制设为 totalMs 以吸收舍入误差。</li>
 *   <li>段 startMs = 该段首行 startMs，endMs = 该段末行 endMs。</li>
 * </ol>
 */
@Service
public class MvTimelineService {

    public static final long MIN_LINE_MS = 800L;

    public record TimedLine(String sectionName, String text, long startMs, long endMs) {}

    public record TimedSection(String name, String mood, long startMs, long endMs, List<TimedLine> lines) {}

    public record Timeline(List<TimedSection> sections, long totalMs, double scaleFactor) {}

    public Timeline align(JsonNode lyricsRoot, long audioDurationMs) {
        if (lyricsRoot == null || !lyricsRoot.has("sections") || !lyricsRoot.get("sections").isArray()
                || lyricsRoot.get("sections").isEmpty()) {
            throw new IllegalArgumentException("作词结果为空");
        }
        ArrayNode sectionsNode = (ArrayNode) lyricsRoot.get("sections");

        List<String> sectionNames = new ArrayList<>();
        List<String> sectionMoods = new ArrayList<>();
        List<List<String>> sectionLines = new ArrayList<>();
        List<long[]> sectionLineWeights = new ArrayList<>();
        List<Long> sectionWeights = new ArrayList<>();
        List<Long> sectionBases = new ArrayList<>();

        long totalEst = 0L;

        for (JsonNode sectionNode : sectionsNode) {
            String name = sectionNode.path("name").asText("");
            String mood = sectionNode.path("mood").asText("");
            int estSeconds = sectionNode.path("estSeconds").asInt(20);
            String lyrics = sectionNode.path("lyrics").asText("");

            List<String> lines = new ArrayList<>();
            String[] raw = lyrics.split("\n", -1);
            for (String r : raw) {
                String t = r.trim();
                if (!t.isEmpty()) {
                    lines.add(t);
                }
            }
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("作词结果含空段落");
            }

            long[] weights = new long[lines.size()];
            long sectionWeight = 0L;
            for (int i = 0; i < lines.size(); i++) {
                int cp = lines.get(i).codePointCount(0, lines.get(i).length());
                if (cp < 1) {
                    cp = 1;
                }
                weights[i] = cp;
                sectionWeight += cp;
            }

            long sectionBase = (long) estSeconds * 1000L;
            totalEst += sectionBase;

            sectionNames.add(name);
            sectionMoods.add(mood);
            sectionLines.add(lines);
            sectionLineWeights.add(weights);
            sectionWeights.add(sectionWeight);
            sectionBases.add(sectionBase);
        }

        double scale = audioDurationMs > 0 ? (double) audioDurationMs / (double) totalEst : 1.0;
        long totalMs = audioDurationMs > 0 ? audioDurationMs : totalEst;

        List<Double> lineDurations = new ArrayList<>();
        for (int s = 0; s < sectionLines.size(); s++) {
            long sectionBase = sectionBases.get(s);
            long sectionWeight = sectionWeights.get(s);
            long[] weights = sectionLineWeights.get(s);
            for (long w : weights) {
                double lineBase = (double) sectionBase * (double) w / (double) sectionWeight;
                lineDurations.add(lineBase * scale);
            }
        }

        double sumAfterClamp = 0.0;
        for (int i = 0; i < lineDurations.size(); i++) {
            double d = lineDurations.get(i);
            if (d < (double) MIN_LINE_MS) {
                d = (double) MIN_LINE_MS;
                lineDurations.set(i, d);
            }
            sumAfterClamp += d;
        }

        if (sumAfterClamp > (double) totalMs && sumAfterClamp > 0.0) {
            double second = (double) totalMs / sumAfterClamp;
            for (int i = 0; i < lineDurations.size(); i++) {
                lineDurations.set(i, lineDurations.get(i) * second);
            }
        }

        List<TimedLine> flatLines = new ArrayList<>();
        long cursor = 0L;
        int flatIndex = 0;
        for (int s = 0; s < sectionLines.size(); s++) {
            List<String> lines = sectionLines.get(s);
            String name = sectionNames.get(s);
            for (String lineText : lines) {
                double d = lineDurations.get(flatIndex);
                long startMs = Math.round((double) cursor);
                long endMs = Math.round((double) cursor + d);
                flatLines.add(new TimedLine(name, lineText, startMs, endMs));
                cursor = endMs;
                flatIndex++;
            }
        }

        if (!flatLines.isEmpty()) {
            TimedLine last = flatLines.get(flatLines.size() - 1);
            flatLines.set(flatLines.size() - 1,
                    new TimedLine(last.sectionName(), last.text(), last.startMs(), totalMs));
        }

        List<TimedSection> sections = new ArrayList<>();
        int idx = 0;
        for (int s = 0; s < sectionLines.size(); s++) {
            int count = sectionLines.get(s).size();
            List<TimedLine> secLines = new ArrayList<>(count);
            for (int i = 0; i < count; i++) {
                secLines.add(flatLines.get(idx++));
            }
            long startMs = secLines.get(0).startMs();
            long endMs = secLines.get(secLines.size() - 1).endMs();
            sections.add(new TimedSection(sectionNames.get(s), sectionMoods.get(s), startMs, endMs, secLines));
        }

        return new Timeline(sections, totalMs, scale);
    }

    /**
     * 纯音乐时间轴：把总时长按 segmentMs 切段，每段一个空文本行（无字幕）。
     */
    public Timeline buildInstrumentalTimeline(long totalMs, long segmentMs) {
        if (totalMs <= 0) {
            throw new IllegalArgumentException("音频时长无效");
        }
        long seg = segmentMs > 0 ? segmentMs : 10000L;
        List<TimedSection> sections = new ArrayList<>();
        long cursor = 0L;
        int n = 1;
        while (cursor < totalMs) {
            long end = Math.min(cursor + seg, totalMs);
            TimedLine line = new TimedLine("段落 " + n, "", cursor, end);
            sections.add(new TimedSection("段落 " + n, "", cursor, end, List.of(line)));
            cursor = end;
            n++;
        }
        return new Timeline(sections, totalMs, 1.0);
    }

    /**
     * 把 toJson 的输出解析回 Timeline。
     */
    public Timeline fromJson(String json) {
        try {
            ObjectMapper mapper = new ObjectMapper();
            JsonNode root = mapper.readTree(json);
            long totalMs = root.path("totalMs").asLong(0L);
            double scale = root.path("scaleFactor").asDouble(1.0);
            List<TimedSection> sections = new ArrayList<>();
            for (JsonNode s : root.path("sections")) {
                List<TimedLine> lines = new ArrayList<>();
                for (JsonNode l : s.path("lines")) {
                    lines.add(new TimedLine(s.path("name").asText(""),
                            l.path("text").asText(""), l.path("startMs").asLong(0L), l.path("endMs").asLong(0L)));
                }
                sections.add(new TimedSection(s.path("name").asText(""), s.path("mood").asText(""),
                        s.path("startMs").asLong(0L), s.path("endMs").asLong(0L), lines));
            }
            if (sections.isEmpty()) {
                throw new IllegalArgumentException("时间轴为空");
            }
            return new Timeline(sections, totalMs, scale);
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("时间轴解析失败");
        }
    }

    public String toJson(Timeline t) {
        try {
            ObjectMapper mapper = new ObjectMapper();
            ObjectNode root = mapper.createObjectNode();
            root.put("totalMs", t.totalMs());
            root.put("scaleFactor", t.scaleFactor());
            ArrayNode sectionsNode = root.putArray("sections");
            for (TimedSection s : t.sections()) {
                ObjectNode sNode = sectionsNode.addObject();
                sNode.put("name", s.name());
                sNode.put("mood", s.mood());
                sNode.put("startMs", s.startMs());
                sNode.put("endMs", s.endMs());
                ArrayNode linesNode = sNode.putArray("lines");
                for (TimedLine l : s.lines()) {
                    ObjectNode lNode = linesNode.addObject();
                    lNode.put("text", l.text());
                    lNode.put("startMs", l.startMs());
                    lNode.put("endMs", l.endMs());
                }
            }
            return mapper.writeValueAsString(root);
        } catch (Exception e) {
            throw new IllegalStateException("时间轴序列化失败", e);
        }
    }
}
