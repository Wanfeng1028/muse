package com.dramafactory.service;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 视频拆解的确定性分析器（纯逻辑，不碰 IO/数据库）。
 *
 * <p>由 ffprobe 实测元数据与 ffmpeg 场景切分点算出分镜段、节奏指标、结构划分与反推提示词。
 * 视觉类字段（主体、画面描述、景别、运镜、光线、调色）不在此推断：提示词中以 [待AI增强]
 * 占位，报告中显式标注口径，杜绝把规则猜测包装成 AI 识别结果。</p>
 */
@Component
public class DeconstructionAnalyzer {

    /** 视频实测元数据（ffprobe）。 */
    public static record VideoMeta(double durationSec, Integer width, Integer height, Double fps, Long bitRate) {
    }

    /** 一段镜头区间（切分合并后的最终分镜）。 */
    public static record ShotSegment(int shotNo, double startSec, double endSec) {
        public double duration() {
            return endSec - startSec;
        }
    }

    /** 分析后的一镜：区间 + 结构角色 + 时长类别 + 两版反推提示词。 */
    public static record AnalyzedShot(ShotSegment segment, String role, String durationClass,
                                      String genericPrompt, String seedancePrompt) {
    }

    /** 全片结构段（钩子/主体/转折/收尾，规则推断）。 */
    public static record StructureSegment(String kind, double startSec, double endSec,
                                          List<Integer> shotNos, String note) {
    }

    /** 切分参数：最短镜、镜数上限、无切分点时的回退采样段长。 */
    public static record Config(double minShotSec, int maxShots, double fallbackSegmentSec) {
    }

    /** 完整分析结果。 */
    public static record Analysis(VideoMeta meta, List<AnalyzedShot> shots, double avgShotDurationSec,
                                  double cutsPerMinute, String rhythmClass, double hookEndSec,
                                  List<StructureSegment> structure, Map<String, Object> formula,
                                  String scriptTemplate, String ratioLabel) {
    }

    private static final String NOTE_HOOK = "开场钩子段：用最短时间给出强信息或强情绪，决定去留。";
    private static final String NOTE_MAIN = "主体段：承载核心内容与信息递进。";
    private static final String NOTE_TURN = "转折段：全片最长镜之一，承担反差、揭秘或情绪拐点。";
    private static final String NOTE_END = "收尾段：收束情绪并给出行动指引（关注/购买/追更）。";

    /**
     * 主分析入口：切分 → 指标 → 结构 → 逐镜提示词 → 公式与剧本模板。
     */
    public Analysis analyze(VideoMeta meta, List<Double> cutTimes, Config cfg) {
        List<ShotSegment> segs = buildSegments(meta.durationSec(), cutTimes, cfg);
        double avg = segs.stream().mapToDouble(ShotSegment::duration).average().orElse(0.0);
        double cpm = segs.size() <= 1 ? 0.0 : (segs.size() - 1) / (meta.durationSec() / 60.0);
        String rhythm = classifyRhythm(avg);
        String ratio = ratioLabel(meta.width(), meta.height());

        double threshold = Math.min(3.0, meta.durationSec() * 0.2);
        double hookEnd = segs.get(0).endSec();
        for (ShotSegment s : segs) {
            if (s.startSec() < threshold) {
                hookEnd = s.endSec();
            }
        }

        List<StructureSegment> structure = buildStructure(meta.durationSec(), segs, avg, hookEnd);

        List<AnalyzedShot> shots = new ArrayList<>();
        for (ShotSegment seg : segs) {
            String role = "主体";
            for (StructureSegment ss : structure) {
                if (ss.shotNos().contains(seg.shotNo())) {
                    role = ss.kind();
                    break;
                }
            }
            String dc = durationClass(seg.duration());
            shots.add(new AnalyzedShot(seg, role, dc,
                    genericPrompt(role, dc, seg.duration(), rhythm, ratio),
                    seedancePrompt(role, dc, seg.duration(), rhythm, ratio)));
        }

        Map<String, Object> formula = buildFormula(structure, rhythm, cpm, avg, hookEnd, shots);
        String scriptTemplate = buildScriptTemplate(structure);
        return new Analysis(meta, shots, avg, cpm, rhythm, hookEnd, structure, formula, scriptTemplate, ratio);
    }

    /**
     * 由切分点构建分镜段：清洗 → 成段 → 合并过短段 → 无有效切分时回退均匀采样 → 超上限合并 → 统一编号。
     */
    public List<ShotSegment> buildSegments(double durationSec, List<Double> cutTimes, Config cfg) {
        if (durationSec <= 0) {
            throw new IllegalArgumentException("视频时长无效");
        }
        List<Double> cleaned = new ArrayList<>();
        if (cutTimes != null) {
            List<Double> sorted = new ArrayList<>(cutTimes);
            Collections.sort(sorted);
            double last = 0.0;
            for (double c : sorted) {
                if (c > 0.05 && c < durationSec - 0.05 && c - last >= 0.05) {
                    cleaned.add(c);
                    last = c;
                }
            }
        }
        List<double[]> spans = new ArrayList<>();
        double prev = 0.0;
        for (double c : cleaned) {
            spans.add(new double[]{prev, c});
            prev = c;
        }
        spans.add(new double[]{prev, durationSec});

        mergeShortSpans(spans, cfg.minShotSec());

        if (spans.size() == 1 && durationSec >= cfg.fallbackSegmentSec() * 2) {
            int n = (int) Math.ceil(durationSec / cfg.fallbackSegmentSec());
            double len = durationSec / n;
            spans.clear();
            for (int i = 0; i < n; i++) {
                spans.add(new double[]{i * len, (i + 1) * len});
            }
        }

        while (spans.size() > cfg.maxShots()) {
            int minIdx = 0;
            for (int i = 1; i < spans.size(); i++) {
                if (spans.get(i)[1] - spans.get(i)[0] < spans.get(minIdx)[1] - spans.get(minIdx)[0]) {
                    minIdx = i;
                }
            }
            if (minIdx == 0) {
                spans.get(1)[0] = spans.get(0)[0];
                spans.remove(0);
            } else if (minIdx == spans.size() - 1) {
                spans.get(minIdx - 1)[1] = spans.get(minIdx)[1];
                spans.remove(minIdx);
            } else {
                double leftLen = spans.get(minIdx - 1)[1] - spans.get(minIdx - 1)[0];
                double rightLen = spans.get(minIdx + 1)[1] - spans.get(minIdx + 1)[0];
                if (leftLen <= rightLen) {
                    spans.get(minIdx - 1)[1] = spans.get(minIdx)[1];
                    spans.remove(minIdx);
                } else {
                    spans.get(minIdx + 1)[0] = spans.get(minIdx)[0];
                    spans.remove(minIdx);
                }
            }
        }

        List<ShotSegment> result = new ArrayList<>();
        for (int i = 0; i < spans.size(); i++) {
            result.add(new ShotSegment(i + 1, spans.get(i)[0], spans.get(i)[1]));
        }
        return Collections.unmodifiableList(result);
    }

    /** 循环合并时长小于 minShotSec 的段：第一段与后段合并，其余与前段合并。 */
    private void mergeShortSpans(List<double[]> spans, double minShotSec) {
        boolean changed = true;
        while (changed && spans.size() > 1) {
            changed = false;
            for (int i = 0; i < spans.size(); i++) {
                double len = spans.get(i)[1] - spans.get(i)[0];
                if (len < minShotSec) {
                    if (i == 0) {
                        spans.get(1)[0] = spans.get(0)[0];
                        spans.remove(0);
                    } else {
                        spans.get(i - 1)[1] = spans.get(i)[1];
                        spans.remove(i);
                    }
                    changed = true;
                    break;
                }
            }
        }
    }

    /** 节奏分类（规则推断）：按平均镜长分档。 */
    public static String classifyRhythm(double avgShotSec) {
        if (avgShotSec < 2.0) {
            return "快节奏";
        }
        if (avgShotSec <= 4.5) {
            return "中节奏";
        }
        return "慢节奏";
    }

    /** 单镜时长类别（规则推断）。 */
    public static String durationClass(double d) {
        if (d < 2.0) {
            return "短切";
        }
        if (d <= 5.0) {
            return "常规";
        }
        return "长镜";
    }

    /** 画幅标签：常见比例优先，否则给出小数比。 */
    public static String ratioLabel(Integer w, Integer h) {
        if (w == null || h == null || w <= 0 || h <= 0) {
            return "未知";
        }
        double r = w / (double) h;
        if (Math.abs(r - 16.0 / 9) < 0.02) {
            return "16:9";
        }
        if (Math.abs(r - 9.0 / 16) < 0.02) {
            return "9:16";
        }
        if (Math.abs(r - 4.0 / 3) < 0.02) {
            return "4:3";
        }
        if (Math.abs(r - 3.0 / 4) < 0.02) {
            return "3:4";
        }
        if (Math.abs(r - 1.0) < 0.02) {
            return "1:1";
        }
        if (Math.abs(r - 21.0 / 9) < 0.02) {
            return "21:9";
        }
        return String.format(Locale.ROOT, "%.2f:1", r);
    }

/**
* 全片结构划分（规则推断）：
* 钩子 = 起始时间早于 hookEnd 的全部段；时长满 10 秒且至少 4 镜时才划分转折/收尾；
* 收尾 = 自 88% 时间点起的尾段（要求钩子与收尾之间至少留 1 镜）；
* 转折 = 45% 之后、收尾之前、时长不低于平均镜长 1.3 倍的最长一镜（并列取靠前者）；
* 其余按相对转折/收尾的位置归为一至两段主体。
*/
private List<StructureSegment> buildStructure(double duration, List<ShotSegment> segs, double avg, double hookEnd) {
List<Integer> hookNos = new ArrayList<>();
for (ShotSegment s: segs) {
if (s.startSec() < hookEnd) {
hookNos.add(s.shotNo());
}
}
List<StructureSegment> out = new ArrayList<>();
out.add(segmentOf("钩子", segs, hookNos, NOTE_HOOK));

if (duration < 10 || segs.size() < 4) {
List<Integer> rest = minusNos(segs, hookNos, List.of());
if (!rest.isEmpty()) {
out.add(segmentOf("主体", segs, rest, NOTE_MAIN));
}
return Collections.unmodifiableList(out);
}

List<Integer> endNos = new ArrayList<>();
for (ShotSegment s: segs) {
if (s.startSec() >= duration * 0.88) {
endNos.add(s.shotNo());
}
}
List<Integer> middleNos = minusNos(segs, hookNos, endNos);
if (endNos.isEmpty() || middleNos.isEmpty()) {
endNos = List.of();
middleNos = minusNos(segs, hookNos, List.of());
}

ShotSegment turn = null;
for (ShotSegment s: segs) {
if (!middleNos.contains(s.shotNo())) {
continue;
}
if (s.startSec() < duration * 0.45 || s.duration() < avg * 1.3) {
continue;
}
if (turn == null || s.duration() > turn.duration()) {
turn = s;
}
}

if (turn == null) {
if (!middleNos.isEmpty()) {
out.add(segmentOf("主体", segs, middleNos, NOTE_MAIN));
}
} else {
List<Integer> before = new ArrayList<>();
List<Integer> after = new ArrayList<>();
for (int no: middleNos) {
if (no == turn.shotNo()) {
continue;
}
ShotSegment s = segs.get(no - 1);
if (s.endSec() <= turn.startSec()) {
before.add(no);
} else {
after.add(no);
}
}
if (!before.isEmpty()) {
out.add(segmentOf("主体", segs, before, NOTE_MAIN));
}
out.add(segmentOf("转折", segs, List.of(turn.shotNo()), NOTE_TURN));
if (!after.isEmpty()) {
out.add(segmentOf("主体", segs, after, NOTE_MAIN));
}
}
if (!endNos.isEmpty()) {
out.add(segmentOf("收尾", segs, endNos, NOTE_END));
}
out.sort(Comparator.comparingDouble(StructureSegment::startSec));
return Collections.unmodifiableList(out);
}

private StructureSegment segmentOf(String kind, List<ShotSegment> segs, List<Integer> nos, String note) {
double start = Double.MAX_VALUE;
double end = 0.0;
for (ShotSegment s: segs) {
if (nos.contains(s.shotNo())) {
start = Math.min(start, s.startSec());
end = Math.max(end, s.endSec());
}
}
return new StructureSegment(kind, start, end, List.copyOf(nos), note);
}

private List<Integer> minusNos(List<ShotSegment> segs, List<Integer> a, List<Integer> b) {
List<Integer> out = new ArrayList<>();
for (ShotSegment s: segs) {
if (!a.contains(s.shotNo()) &&!b.contains(s.shotNo())) {
out.add(s.shotNo());
}
}
return out;
}

private String genericPrompt(String role, String dc, double d, String rhythm, String ratio) {
return "主体：[待AI增强]；动作：[待AI增强]；场景：[待AI增强]；镜头：" + role + "段镜头（结构角色，规则推断），"
+ dc + "；节奏：本镜 " + fmt(d) + " 秒，全片" + rhythm + "；画幅：" + ratio
+ "；光线：[待AI增强]；风格：[待AI增强]。";
}

private String seedancePrompt(String role, String dc, double d, String rhythm, String ratio) {
return "主体：[待AI增强]；动作：[待AI增强]；场景：[待AI增强]；镜头：" + role + "段，" + dc
+ "镜头；光线：[待AI增强]；风格：短视频" + rhythm + "剪辑（规则推断）；时长：" + fmt(d)
+ " 秒；画幅：" + ratio + "。";
}

private Map<String, Object> buildFormula(List<StructureSegment> structure, String rhythm, double cpm,
double avg, double hookEnd, List<AnalyzedShot> shots) {
StringBuilder template = new StringBuilder();
for (StructureSegment ss: structure) {
if (template.length() > 0) {
template.append("→");
}
template.append(ss.kind());
}
long shortCount = shots.stream().filter(s -> "短切".equals(s.durationClass())).count();
long normalCount = shots.stream().filter(s -> "常规".equals(s.durationClass())).count();
long longCount = shots.stream().filter(s -> "长镜".equals(s.durationClass())).count();
double total = Math.max(1, shots.size());
double shortPct = round1(shortCount * 100.0 / total);
double normalPct = round1(normalCount * 100.0 / total);
double longPct = round1(longCount * 100.0 / total);

Map<String, Object> composition = new LinkedHashMap<>();
composition.put("短切占比", shortPct);
composition.put("常规占比", normalPct);
composition.put("长镜占比", longPct);

String n2;
if ("快节奏".equals(rhythm)) {
n2 = "节奏公式：平均镜长 " + fmt(avg) + " 秒、每分钟 " + fmt(cpm) + " 切，靠高信息密度留人，适合强冲突题材。";
} else if ("中节奏".equals(rhythm)) {
n2 = "节奏公式：平均镜长 " + fmt(avg) + " 秒、每分钟 " + fmt(cpm) + " 切，信息与呼吸感平衡，适合叙事型内容。";
} else {
n2 = "节奏公式：平均镜长 " + fmt(avg) + " 秒、每分钟 " + fmt(cpm) + " 切，长镜叙事靠内容本身与表演留人。";
}
List<String> notes = List.of(
"结构公式：" + template + "，钩子段 " + fmt(hookEnd) + " 秒内完成开场。",
n2,
"镜头构成：短切 " + fmt(shortPct) + "% / 常规 " + fmt(normalPct) + "% / 长镜 " + fmt(longPct)
+ "%（按时长类别统计，规则推断）。");

Map<String, Object> formula = new LinkedHashMap<>();
formula.put("structureTemplate", template.toString());
formula.put("rhythmClass", rhythm);
formula.put("cutsPerMinute", round1(cpm));
formula.put("avgShotDurationSec", round1(avg));
formula.put("hookDurationSec", round1(hookEnd));
formula.put("shotCount", shots.size());
formula.put("composition", composition);
formula.put("notes", notes);
return formula;
}

private String buildScriptTemplate(List<StructureSegment> structure) {
StringBuilder sb = new StringBuilder();
for (StructureSegment ss: structure) {
if (sb.length() > 0) {
sb.append("\n\n");
}
sb.append("【").append(ss.kind()).append("】")
.append(fmt(ss.startSec())).append("s–").append(fmt(ss.endSec())).append("s（")
.append(ss.shotNos().size()).append(" 镜）\n写法要点：").append(ss.note())
.append("\n主体/台词：______（按你的题材填充）");
}
return sb.toString();
}

private String fmt(double v) {
return String.format(Locale.ROOT, "%.1f", v);
}

private double round1(double v) {
return Math.round(v * 10) / 10.0;
}
}
