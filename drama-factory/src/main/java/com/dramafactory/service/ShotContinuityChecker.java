package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * 分镜连续性校验器。
 *
 * <p>对相邻分镜做静态检查，只报告不自动修改，误报率优先：拿不准的一律不报或标 INFO。
 * 覆盖景别跳变、节奏单调、推拉对冲、180 度轴线、问句承接等常见连续性问题。</p>
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
     * 对分镜列表做连续性检查。
     *
     * @param shots 分镜列表，可为 null 或空
     * @return 连续性报告
     */
    public ContinuityReport check(List<Shot> shots) {
        if (shots == null || shots.isEmpty()) {
            return new ContinuityReport(new ArrayList<>(), 0);
        }

        // 复制后按 shotNo 排序，shotNo 为 null 的排最后；不修改原 list
        List<Shot> sorted = new ArrayList<>(shots);
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
