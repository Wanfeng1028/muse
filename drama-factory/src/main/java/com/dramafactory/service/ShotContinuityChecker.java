package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 分镜连续性校验器。
 *
 * <p>对相邻分镜做静态检查，只报告不自动修改，误报率优先：拿不准的一律不报或标 INFO。
 * 覆盖景别跳变、节奏单调、推拉对冲、180 度轴线、问句承接等常见连续性问题，
 * 以及 R6 节奏校验（目标时长偏差、单镜时长越界、对白覆盖错位）与
 * R7 变异检查（景别单一化、空洞陈词、运镜重复）。R8 为预留规则号。</p>
 */
@Service
public class ShotContinuityChecker {

    /** 严重级别。 */
    public enum Severity {
        /** 警告。 */
        WARN("警告"),
        /** 提示。 */
        INFO("提示");

        /** 中文标签。 */
        private final String label;

        Severity(String label) {
            this.label = label;
        }

        /**
         * 获取中文标签。
         *
         * @return 中文标签
         */
        public String getLabel() {
            return label;
        }
    }

    /**
     * 单条连续性问题。
     *
     * @param shotNo     镜号
     * @param shotId     分镜 ID
     * @param rule       规则名
     * @param severity   严重级别
     * @param message    问题描述
     * @param suggestion 建议
     */
    public record ContinuityIssue(int shotNo, Long shotId, String rule, Severity severity,
                                  String message, String suggestion) {
    }

    /**
     * 连续性检查报告。
     *
     * @param issues      问题列表
     * @param shotsChecked 已检查的分镜数
     */
    public record ContinuityReport(List<ContinuityIssue> issues, int shotsChecked) {

        /**
         * 是否包含警告级别的问题。
         *
         * @return 含 WARN 返回 true
         */
        public boolean hasWarnings() {
            return issues.stream().anyMatch(i -> i.severity() == Severity.WARN);
        }
    }

    /**
     * 节奏校验配置（R6 用；R7 的景别占比阈值也取自此处）。
     *
     * @param targetDurationSeconds 剧集目标时长（秒），null 表示不做总量偏差校验
     * @param minShotSeconds        单镜最小时长（秒）
     * @param maxShotSeconds        单镜最大时长（秒）
     * @param warnDeviationPct      总量偏差达到此百分比记 WARN
     * @param infoDeviationPct      总量偏差达到此百分比记 INFO
     * @param shotSizeDominancePct  同一景别占比达到此比例记景别单一（R7）
     */
    public record PacingConfig(Integer targetDurationSeconds,
                               double minShotSeconds,
                               double maxShotSeconds,
                               double warnDeviationPct,
                               double infoDeviationPct,
                               double shotSizeDominancePct) {

        /**
         * 默认配置：单镜 2s~15s，总量偏差 WARN 不低于 15%、INFO 不低于 8%，景别占比不低于 60% 告警。
         *
         * @param targetDurationSeconds 剧集目标时长（秒），可为 null
         * @return 默认配置
         */
        public static PacingConfig defaults(Integer targetDurationSeconds) {
            return new PacingConfig(targetDurationSeconds, 2.0, 15.0, 15.0, 8.0, 0.6);
        }
    }

    /**
     * 对分镜列表做连续性检查（R1-R5 + R7，不做节奏校验）。
     *
     * @param shots 分镜列表，可为 null 或空
     * @return 连续性报告
     */
    public ContinuityReport check(List<Shot> shots) {
        return check(shots, null);
    }

    /**
     * 对分镜列表做连续性检查（R1-R5 + R7），并在 pacing 非 null 时追加 R6 节奏校验。
     *
     * @param shots  分镜列表，可为 null 或空
     * @param pacing 节奏校验配置，null 表示跳过 R6
     * @return 连续性报告
     */
    public ContinuityReport check(List<Shot> shots, PacingConfig pacing) {
        if (shots == null || shots.isEmpty()) {
            return new ContinuityReport(new ArrayList<>(), 0);
        }

        // 复制后按 shotNo 排序，shotNo 为 null 的排最后；null 元素直接丢弃（与后继逐对检查的 null 容忍语义一致）；不修改原 list
        List<Shot> sorted = new ArrayList<>();
        for (Shot s : shots) {
            if (s != null) {
                sorted.add(s);
            }
        }
        sorted.sort(Comparator.comparing(Shot::getShotNo, Comparator.nullsLast(Comparator.naturalOrder())));

        List<ContinuityIssue> issues = new ArrayList<>();

        // 逐对相邻检查
        for (int i = 0; i + 1 < sorted.size(); i++) {
            Shot a = sorted.get(i);
            Shot b = sorted.get(i + 1);
            if (a == null || b == null) {
                continue;
            }
            checkShotSizeJump(a, b, issues);
            checkPushPull(a, b, issues);
            checkAxisJump(a, b, issues);
            checkDialogueHandoff(a, b, issues);
        }

        // R2 单调连续段
        checkMonotonousRun(sorted, issues);

        // R6 节奏校验（仅 pacing 非 null 时执行）
        if (pacing != null) {
            checkTargetDeviation(sorted, issues, pacing);
            checkShotDurationBounds(sorted, issues, pacing);
            checkDialogueCoverage(sorted, issues);
        }

        // R7 变异检查
        checkShotSizeDominance(sorted, issues, pacing == null ? 0.6 : pacing.shotSizeDominancePct());
        checkGenericPhrases(sorted, issues);
        checkRepeatedCameraMove(sorted, issues);

        // 按 shotNo 升序
        issues.sort(Comparator.comparingInt(ContinuityIssue::shotNo));

        return new ContinuityReport(issues, sorted.size());
    }

    /**
     * R1：景别跳变。
     */
    private void checkShotSizeJump(Shot a, Shot b, List<ContinuityIssue> issues) {
        ShotSize sizeA = a.getShotSize();
        ShotSize sizeB = b.getShotSize();
        if (sizeA == null || sizeB == null) {
            return;
        }
        int rankA = shotSizeRank(sizeA);
        int rankB = shotSizeRank(sizeB);
        int diff = Math.abs(rankA - rankB);
        if (diff >= 3) {
            String msg = "景别从「" + sizeA.getLabel() + "」直接跳到「" + sizeB.getLabel()
                    + "」（跨" + diff + "级）";
            issues.add(new ContinuityIssue(
                    safeShotNo(b),
                    b.getId(),
                    "SHOT_SIZE_JUMP",
                    Severity.WARN,
                    msg,
                    "建议中间加过渡镜头，或确认为有意的跳切"));
        }
    }

    /**
     * R2：连续多镜景别与运镜完全相同。
     */
    private void checkMonotonousRun(List<Shot> sorted, List<ContinuityIssue> issues) {
        int i = 0;
        int n = sorted.size();
        while (i < n) {
            Shot cur = sorted.get(i);
            if (cur == null || cur.getShotSize() == null || cur.getCameraMove() == null) {
                i++;
                continue;
            }
            ShotSize size = cur.getShotSize();
            CameraMove move = cur.getCameraMove();
            int j = i + 1;
            while (j < n) {
                Shot next = sorted.get(j);
                if (next == null || next.getShotSize() != size || next.getCameraMove() != move) {
                    break;
                }
                j++;
            }
            int runLen = j - i;
            if (runLen >= 3) {
                Shot last = sorted.get(j - 1);
                String msg = "连续" + runLen + "镜景别+运镜完全相同";
                issues.add(new ContinuityIssue(
                        safeShotNo(last),
                        last.getId(),
                        "MONOTONOUS_RUN",
                        Severity.INFO,
                        msg,
                        "建议变化景别或运镜，打破节奏单调"));
            }
            i = j;
        }
    }

    /**
     * R3：推镜头紧接拉镜头。
     */
    private void checkPushPull(Shot a, Shot b, List<ContinuityIssue> issues) {
        CameraMove moveA = a.getCameraMove();
        CameraMove moveB = b.getCameraMove();
        if (moveA == null || moveB == null) {
            return;
        }
        if ("推镜头".equals(moveA.getLabel()) && "拉镜头".equals(moveB.getLabel())) {
            issues.add(new ContinuityIssue(
                    safeShotNo(b),
                    b.getId(),
                    "PUSH_PULL",
                    Severity.INFO,
                    "推镜头后紧接拉镜头",
                    "请确认为有意设计，否则建议统一运镜方向"));
        }
    }

    /**
     * R4：相邻两镜左右方向相反，疑似跳轴。
     */
    private void checkAxisJump(Shot a, Shot b, List<ContinuityIssue> issues) {
        String textA = concatText(a);
        String textB = concatText(b);

        String[] leftKeys = {"左", "向左", "往左", "朝左", "从左", "左侧", "左边"};
        String[] rightKeys = {"右", "向右", "往右", "朝右", "从右", "右侧", "右边"};

        int leftA = countDistinct(textA, leftKeys);
        int rightA = countDistinct(textA, rightKeys);
        int leftB = countDistinct(textB, leftKeys);
        int rightB = countDistinct(textB, rightKeys);

        Boolean dirA = resolveDirection(leftA, rightA);
        Boolean dirB = resolveDirection(leftB, rightB);
        if (dirA == null || dirB == null) {
            return;
        }
        // dirA/dirB：true 表示偏左，false 表示偏右
        if (dirA != dirB) {
            issues.add(new ContinuityIssue(
                    safeShotNo(b),
                    b.getId(),
                    "AXIS_JUMP",
                    Severity.WARN,
                    "相邻两镜方向相反（左/右），疑似违反180度轴线",
                    "检查两镜机位是否跳轴，必要时调整其中一镜的方向描述"));
        }
    }

    /**
     * R5：上一镜以问句结尾，下一镜无对白承接。
     */
    private void checkDialogueHandoff(Shot a, Shot b, List<ContinuityIssue> issues) {
        String dialogueA = a.getDialogue();
        if (dialogueA == null) {
            return;
        }
        String trimmedA = dialogueA.trim();
        if (trimmedA.isEmpty()) {
            return;
        }
        char last = trimmedA.charAt(trimmedA.length() - 1);
        if (last != '?' && last != '？') {
            return;
        }
        String dialogueB = b.getDialogue();
        if (dialogueB != null && !dialogueB.trim().isEmpty()) {
            return;
        }
        String textB = nullToEmpty(b.getDescription()) + " " + nullToEmpty(b.getVideoPrompt());
        String[] responseKeys = {"回应", "回答", "点头", "摇头", "应答", "接话", "应声"};
        for (String key : responseKeys) {
            if (textB.contains(key)) {
                return;
            }
        }
        issues.add(new ContinuityIssue(
                safeShotNo(b),
                b.getId(),
                "DIALOGUE_HANDOFF",
                Severity.INFO,
                "上一镜以问句结尾，下一镜无对白承接",
                "请检查下一镜是否有回应动作或对白承接"));
    }

    /**
     * 中文空洞陈词表（自行编写）：命中分镜描述或提示词时提示具体化。
     */
    private static final List<String> GENERIC_PHRASES_ZH = List.of(
            "美丽的", "震撼的", "完美的", "极致的", "梦幻的",
            "华丽的", "精美的", "惊艳的", "壮观的", "迷人的",
            "炫酷的", "绝美的", "恢弘的", "唯美的", "空灵的",
            "史诗般", "令人惊叹", "无与伦比", "前所未有", "世界级");

    /**
     * 英文空洞陈词表（自行编写）：大小写不敏感，按词边界匹配。
     */
    private static final List<String> GENERIC_PHRASES_EN = List.of(
            "a beautiful", "stunning", "breathtaking", "amazing", "incredible",
            "spectacular", "gorgeous", "mesmerizing", "astonishing", "seamless",
            "jaw-dropping", "mind-blowing", "awe-inspiring", "out of this world", "next level",
            "game-changing", "cutting edge", "state of the art", "top-notch", "world-class");

    /**
     * R6a：分镜时长总和 vs 剧集目标时长偏差。偏差达阈值记 WARN/INFO，否则不报。
     */
    private void checkTargetDeviation(List<Shot> sorted, List<ContinuityIssue> issues, PacingConfig pacing) {
        Integer target = pacing.targetDurationSeconds();
        if (target == null || target <= 0) {
            return;
        }
        long total = 0;
        int withDuration = 0;
        for (Shot s : sorted) {
            if (s != null && s.getDurationSeconds() != null && s.getDurationSeconds() > 0) {
                total += s.getDurationSeconds();
                withDuration++;
            }
        }
        if (withDuration == 0) {
            return;
        }
        double devPct = Math.abs(total - target) * 100.0 / target;
        Severity severity = null;
        if (devPct >= pacing.warnDeviationPct()) {
            severity = Severity.WARN;
        } else if (devPct >= pacing.infoDeviationPct()) {
            severity = Severity.INFO;
        }
        if (severity == null) {
            return;
        }
        Shot anchor = lastNonNull(sorted);
        if (anchor == null) {
            return;
        }
        issues.add(new ContinuityIssue(
                safeShotNo(anchor),
                anchor.getId(),
                "PACING_TOTAL_DEVIATION",
                severity,
                "分镜时长总和 " + total + "s，与目标时长 " + target + "s 偏差 "
                        + String.format("%.1f", devPct) + "%（" + withDuration + " 镜有时长数据）",
                "检查分镜时长分配，增删镜头或调整单镜时长"));
    }

    /**
     * R6b：单镜时长越界（小于 minShotSeconds 或大于 maxShotSeconds）记 WARN。
     */
    private void checkShotDurationBounds(List<Shot> sorted, List<ContinuityIssue> issues, PacingConfig pacing) {
        for (Shot s : sorted) {
            if (s == null || s.getDurationSeconds() == null) {
                continue;
            }
            int d = s.getDurationSeconds();
            if (d < pacing.minShotSeconds() || d > pacing.maxShotSeconds()) {
                issues.add(new ContinuityIssue(
                        safeShotNo(s),
                        s.getId(),
                        "SHOT_DURATION_OUT_OF_RANGE",
                        Severity.WARN,
                        "单镜时长 " + d + "s，超出建议区间 ["
                                + pacing.minShotSeconds() + "s, " + pacing.maxShotSeconds() + "s]",
                        "确认是否为有意设计（如快闪/长镜头），否则调整该镜时长"));
            }
        }
    }

    /**
     * R6c：对白估算朗读时长与分镜时长总和错位提示（启发式估算，仅 INFO）。
     */
    private void checkDialogueCoverage(List<Shot> sorted, List<ContinuityIssue> issues) {
        double speechTotal = 0.0;
        long durationTotal = 0;
        for (Shot s : sorted) {
            if (s == null) {
                continue;
            }
            speechTotal += estimateSpeechSeconds(s.getDialogue());
            if (s.getDurationSeconds() != null && s.getDurationSeconds() > 0) {
                durationTotal += s.getDurationSeconds();
            }
        }
        if (speechTotal <= 0 || durationTotal <= 0) {
            return;
        }
        if (speechTotal <= durationTotal * 1.25) {
            return;
        }
        Shot anchor = lastNonNull(sorted);
        if (anchor == null) {
            return;
        }
        double ratio = speechTotal / durationTotal;
        issues.add(new ContinuityIssue(
                safeShotNo(anchor),
                anchor.getId(),
                "DIALOGUE_COVERAGE_MISMATCH",
                Severity.INFO,
                "对白估算朗读时长约 " + String.format("%.1f", speechTotal) + "s，为分镜时长总和 "
                        + durationTotal + "s 的 " + String.format("%.1f", ratio)
                        + " 倍，旁白/对白可能放不下（启发式估算，仅供参考）",
                "删减对白、拆分到更多镜头，或延长相关分镜时长"));
    }

    /**
     * 估算对白朗读秒数：中文字符约 0.30s/字，拉丁字符按 5 字符折一词、约 0.40s/词。
     * 启发式估算，不追求精确。
     */
    private static double estimateSpeechSeconds(String dialogue) {
        if (dialogue == null) {
            return 0.0;
        }
        String text = dialogue.trim();
        if (text.isEmpty()) {
            return 0.0;
        }
        int cjk = 0;
        int other = 0;
        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            if (isCjk(cp)) {
                cjk++;
            } else if (!Character.isWhitespace(cp)) {
                other++;
            }
            i += Character.charCount(cp);
        }
        return cjk * 0.30 + (other / 5.0) * 0.40;
    }

    /**
     * 是否中日韩表意字符或全角/半角兼容区字符。
     */
    private static boolean isCjk(int cp) {
        return (cp >= 0x4E00 && cp <= 0x9FFF)
                || (cp >= 0x3400 && cp <= 0x4DBF)
                || (cp >= 0x3000 && cp <= 0x303F)
                || (cp >= 0xFF00 && cp <= 0xFFEF);
    }

    /**
     * R7a：全集景别单一化。有效景别不少于 4 镜，且同一景别占比达到阈值时记 WARN。
     */
    private void checkShotSizeDominance(List<Shot> sorted, List<ContinuityIssue> issues, double dominancePct) {
        Map<ShotSize, Integer> counts = new EnumMap<>(ShotSize.class);
        int n = 0;
        for (Shot s : sorted) {
            if (s != null && s.getShotSize() != null) {
                counts.merge(s.getShotSize(), 1, Integer::sum);
                n++;
            }
        }
        if (n < 4) {
            return;
        }
        ShotSize top = null;
        int topCount = 0;
        for (Map.Entry<ShotSize, Integer> e : counts.entrySet()) {
            if (e.getValue() > topCount) {
                top = e.getKey();
                topCount = e.getValue();
            }
        }
        if (top == null || topCount < n * dominancePct) {
            return;
        }
        Shot anchor = lastNonNull(sorted);
        if (anchor == null) {
            return;
        }
        double pct = topCount * 100.0 / n;
        issues.add(new ContinuityIssue(
                safeShotNo(anchor),
                anchor.getId(),
                "SHOT_SIZE_DOMINANCE",
                Severity.WARN,
                "全集 " + n + " 镜中「" + top.getLabel() + "」出现 " + topCount
                        + " 次（占比 " + String.format("%.0f", pct) + "%），景别过于单一",
                "穿插远景建立镜头与特写，打破视觉单调"));
    }

    /**
     * R7b：分镜描述/videoPrompt 命中空洞陈词时提示具体化（每镜最多一条，INFO）。
     */
    private void checkGenericPhrases(List<Shot> sorted, List<ContinuityIssue> issues) {
        for (Shot s : sorted) {
            if (s == null) {
                continue;
            }
            String text = nullToEmpty(s.getDescription()) + "\n" + nullToEmpty(s.getVideoPrompt());
            if (text.isBlank()) {
                continue;
            }
            List<String> hits = new ArrayList<>();
            for (String phrase : GENERIC_PHRASES_ZH) {
                if (text.contains(phrase)) {
                    hits.add(phrase);
                }
            }
            String lower = text.toLowerCase();
            for (String phrase : GENERIC_PHRASES_EN) {
                Pattern p = Pattern.compile("\\b" + Pattern.quote(phrase) + "\\b", Pattern.CASE_INSENSITIVE);
                if (p.matcher(lower).find()) {
                    hits.add(phrase);
                }
            }
            if (hits.isEmpty()) {
                continue;
            }
            List<String> shown = hits.size() > 3 ? hits.subList(0, 3) : hits;
            issues.add(new ContinuityIssue(
                    safeShotNo(s),
                    s.getId(),
                    "GENERIC_PHRASE",
                    Severity.INFO,
                    "描述/提示词含空洞陈词「" + String.join("、", shown) + "」，建议替换为具体视觉细节",
                    "把形容词换成可被画出来的细节：光线、材质、动作、空间关系"));
        }
    }

    /**
     * R7c：连续相同运镜达到 3 镜及以上时提示（每段一条，INFO）。
     */
    private void checkRepeatedCameraMove(List<Shot> sorted, List<ContinuityIssue> issues) {
        int i = 0;
        int n = sorted.size();
        while (i < n) {
            Shot cur = sorted.get(i);
            if (cur == null || cur.getCameraMove() == null) {
                i++;
                continue;
            }
            CameraMove move = cur.getCameraMove();
            int j = i + 1;
            while (j < n) {
                Shot next = sorted.get(j);
                if (next == null || next.getCameraMove() != move) {
                    break;
                }
                j++;
            }
            int runLen = j - i;
            if (runLen >= 3) {
                Shot last = sorted.get(j - 1);
                issues.add(new ContinuityIssue(
                        safeShotNo(last),
                        last == null ? null : last.getId(),
                        "REPEATED_CAMERA_MOVE",
                        Severity.INFO,
                        "连续 " + runLen + " 镜运镜相同（" + move.getLabel() + "）",
                        "穿插推拉、摇移等不同运镜，增强节奏变化"));
            }
            i = j;
        }
    }

    /**
     * 取列表中最后一个非 null 分镜；全为 null 返回 null。
     */
    private Shot lastNonNull(List<Shot> sorted) {
        for (int i = sorted.size() - 1; i >= 0; i--) {
            if (sorted.get(i) != null) {
                return sorted.get(i);
            }
        }
        return null;
    }

    /**
     * 拼接用于方向判断的文本。
     */
    private String concatText(Shot shot) {
        return nullToEmpty(shot.getDescription()) + " "
                + nullToEmpty(shot.getVideoPrompt()) + " "
                + nullToEmpty(shot.getDialogue());
    }

    /**
     * 统计文本中命中的去重关键词个数。
     */
    private int countDistinct(String text, String[] keys) {
        int count = 0;
        for (String key : keys) {
            if (text.contains(key)) {
                count++;
            }
        }
        return count;
    }

    /**
     * 依据左右命中数判定明确方向：一侧>0 且另一侧==0 记为该侧明确，否则返回 null。
     *
     * @return true 表示明确偏左，false 表示明确偏右，null 表示方向不明
     */
    private Boolean resolveDirection(int leftCount, int rightCount) {
        if (leftCount > 0 && rightCount == 0) {
            return Boolean.TRUE;
        }
        if (rightCount > 0 && leftCount == 0) {
            return Boolean.FALSE;
        }
        return null;
    }

    /**
     * 景别序：特写=0、近景=1、中景=2、全景=3、远景=4。
     */
    private int shotSizeRank(ShotSize size) {
        switch (size) {
            case TE_XIE:
                return 0;
            case JIN_JING:
                return 1;
            case ZHONG_JING:
                return 2;
            case QUAN_JING:
                return 3;
            case YUAN_JING:
                return 4;
            default:
                return 0;
        }
    }

    /**
     * 安全取镜号，null 返回 0。
     */
    private int safeShotNo(Shot shot) {
        Integer no = shot.getShotNo();
        return no == null ? 0 : no;
    }

    /**
     * null 转空字符串。
     */
    private String nullToEmpty(String s) {
        return s == null ? "" : s;
    }
}
