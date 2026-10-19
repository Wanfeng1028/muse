package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link ShotContinuityChecker} 的纯单测，覆盖 R6 节奏校验与 R7 变异检查。
 *
 * <p>不依赖 Spring/DB/网络，直接 new 出校验器实例。</p>
 */
class ShotContinuityCheckerQualityTest {

    /** 被测对象。 */
    private final ShotContinuityChecker checker = new ShotContinuityChecker();

    /**
     * 构造一个分镜。
     *
     * @param no              镜号
     * @param size            景别
     * @param move            运镜
     * @param durationSeconds 时长（秒）
     * @param desc            描述
     * @param dialogue        对白
     * @param videoPrompt     视频提示词
     * @return 分镜对象
     */
    private Shot shot(int no, ShotSize size, CameraMove move, Integer durationSeconds,
                      String desc, String dialogue, String videoPrompt) {
        Shot s = new Shot();
        s.setShotNo(no);
        s.setShotSize(size);
        s.setCameraMove(move);
        s.setDurationSeconds(durationSeconds);
        s.setDescription(desc);
        s.setDialogue(dialogue);
        s.setVideoPrompt(videoPrompt);
        return s;
    }

    /**
     * 按规则名过滤问题列表。
     *
     * @param report 报告
     * @param rule   规则名
     * @return 命中该规则的问题列表
     */
    private List<ShotContinuityChecker.ContinuityIssue> issuesByRule(
            ShotContinuityChecker.ContinuityReport report, String rule) {
        List<ShotContinuityChecker.ContinuityIssue> result = new ArrayList<>();
        for (ShotContinuityChecker.ContinuityIssue issue : report.issues()) {
            if (rule.equals(issue.rule())) {
                result.add(issue);
            }
        }
        return result;
    }

    // ---------------- R6a PACING_TOTAL_DEVIATION ----------------

    @Test
    @DisplayName("R6a：4 镜时长总和 100，目标 80 → 偏差 25% → 1 条 WARN")
    void pacingTotalDeviationWarn() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d3", null, null),
                shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(80));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "PACING_TOTAL_DEVIATION");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.WARN, issues.get(0).severity());
    }

    @Test
    @DisplayName("R6a：4 镜时长总和 100，目标 90 → 偏差约 11.1% → 1 条 INFO")
    void pacingTotalDeviationInfo() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d3", null, null),
                shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(90));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "PACING_TOTAL_DEVIATION");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, issues.get(0).severity());
    }

    @Test
    @DisplayName("R6a：4 镜时长总和 100，目标 100 → 偏差 0% → 0 条")
    void pacingTotalDeviationExactMatch() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d3", null, null),
                shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(100));

        assertEquals(0, issuesByRule(report, "PACING_TOTAL_DEVIATION").size());
    }

    @Test
    @DisplayName("R6a：check(shots) 不带 pacing → 0 条 PACING_TOTAL_DEVIATION")
    void pacingTotalDeviationNoPacingArgument() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d3", null, null),
                shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        assertEquals(0, issuesByRule(report, "PACING_TOTAL_DEVIATION").size());
    }

    @Test
    @DisplayName("R6a：目标时长为 null → 0 条")
    void pacingTotalDeviationNullTarget() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d3", null, null),
                shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, 25, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "PACING_TOTAL_DEVIATION").size());
    }

    @Test
    @DisplayName("R6a：全部时长 null → 0 条")
    void pacingTotalDeviationNoDurations() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d3", null, null),
                shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(80));

        assertEquals(0, issuesByRule(report, "PACING_TOTAL_DEVIATION").size());
    }

    // ---------------- R6b SHOT_DURATION_OUT_OF_RANGE ----------------

    @Test
    @DisplayName("R6b：单镜时长 1 → 1 条 WARN")
    void shotDurationTooShort() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 1, "d1", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "SHOT_DURATION_OUT_OF_RANGE");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.WARN, issues.get(0).severity());
    }

    @Test
    @DisplayName("R6b：单镜时长 16 → 1 条 WARN")
    void shotDurationTooLong() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 16, "d1", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "SHOT_DURATION_OUT_OF_RANGE");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.WARN, issues.get(0).severity());
    }

    @Test
    @DisplayName("R6b：单镜时长 5 → 0 条")
    void shotDurationInRange() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 5, "d1", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "SHOT_DURATION_OUT_OF_RANGE").size());
    }

    @Test
    @DisplayName("R6b：时长为 null 的镜不触发越界")
    void shotDurationNullNotReported() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d1", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "SHOT_DURATION_OUT_OF_RANGE").size());
    }

    // ---------------- R6c DIALOGUE_COVERAGE_MISMATCH ----------------

    @Test
    @DisplayName("R6c：对白 20 个中文字符估算 6.0s，时长 4s → 1 条 INFO")
    void dialogueCoverageMismatch() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 4, "d1", "啊".repeat(20), null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "DIALOGUE_COVERAGE_MISMATCH");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, issues.get(0).severity());
    }

    @Test
    @DisplayName("R6c：对白 10 个中文字符估算 3.0s，时长 10s → 0 条")
    void dialogueCoverageFits() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 10, "d1", "啊".repeat(10), null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "DIALOGUE_COVERAGE_MISMATCH").size());
    }

    @Test
    @DisplayName("R6c：对白全空 → 0 条")
    void dialogueCoverageEmptyDialogue() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, 4, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, 4, "d2", "   ", null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "DIALOGUE_COVERAGE_MISMATCH").size());
    }

    // ---------------- R7a SHOT_SIZE_DOMINANCE ----------------

    @Test
    @DisplayName("R7a：4 镜全部中景 → 1 条 WARN，message 含「占比」")
    void shotSizeDominanceWarn() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d3", null, null),
                shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "SHOT_SIZE_DOMINANCE");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.WARN, issues.get(0).severity());
        assertTrue(issues.get(0).message().contains("占比"));
    }

    @Test
    @DisplayName("R7a：仅 3 镜全部中景 → 0 条（有效景别不足 4）")
    void shotSizeDominanceTooFewShots() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d3", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "SHOT_SIZE_DOMINANCE").size());
    }

    @Test
    @DisplayName("R7a：4 镜景别各不相同 → 0 条")
    void shotSizeDominanceAllDistinct() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, null, "d1", null, null),
                shot(2, ShotSize.JIN_JING, CameraMove.YAO, null, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.TUI, null, "d3", null, null),
                shot(4, ShotSize.YUAN_JING, CameraMove.LA, null, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "SHOT_SIZE_DOMINANCE").size());
    }

    // ---------------- R7b GENERIC_PHRASE ----------------

    @Test
    @DisplayName("R7b：描述含「美丽的」 → 1 条 INFO，message 含「美丽的」")
    void genericPhraseChinese() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "这是一个美丽的日落", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "GENERIC_PHRASE");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, issues.get(0).severity());
        assertTrue(issues.get(0).message().contains("美丽的"));
    }

    @Test
    @DisplayName("R7b：videoPrompt 英文大小写不敏感命中 → 1 条 INFO")
    void genericPhraseEnglishCaseInsensitive() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, null, null,
                        "A beautiful cityscape, STUNNING view"));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "GENERIC_PHRASE");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, issues.get(0).severity());
    }

    @Test
    @DisplayName("R7b：无空洞陈词 → 0 条")
    void genericPhraseClean() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "人物走过街道", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "GENERIC_PHRASE").size());
    }

    // ---------------- R7c REPEATED_CAMERA_MOVE ----------------

    @Test
    @DisplayName("R7c：3 镜连续固定 → 1 条 INFO")
    void repeatedCameraMoveThree() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, null, "d1", null, null),
                shot(2, ShotSize.JIN_JING, CameraMove.GU_DING, null, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d3", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        List<ShotContinuityChecker.ContinuityIssue> issues =
                issuesByRule(report, "REPEATED_CAMERA_MOVE");
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, issues.get(0).severity());
    }

    @Test
    @DisplayName("R7c：2 镜连续固定 → 0 条")
    void repeatedCameraMoveTwo() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, null, "d1", null, null),
                shot(2, ShotSize.JIN_JING, CameraMove.GU_DING, null, "d2", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "REPEATED_CAMERA_MOVE").size());
    }

    @Test
    @DisplayName("R7c：运镜交替 → 0 条")
    void repeatedCameraMoveAlternating() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, null, "d1", null, null),
                shot(2, ShotSize.JIN_JING, CameraMove.YAO, null, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d3", null, null));

        ShotContinuityChecker.ContinuityReport report =
                checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(null));

        assertEquals(0, issuesByRule(report, "REPEATED_CAMERA_MOVE").size());
    }

    // ---------------- 回归语义 ----------------

    @Test
    @DisplayName("回归：check(List) 无 pacing 时仍执行 R7；有景别单一、无总量偏差")
    void regressionR7RunsWithoutPacing() {
        List<Shot> shots = List.of(
                shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d1", null, null),
                shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d2", null, null),
                shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d3", null, null),
                shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, null, "d4", null, null));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        assertEquals(4, report.shotsChecked());
        assertFalse(issuesByRule(report, "SHOT_SIZE_DOMINANCE").isEmpty());
        assertEquals(0, issuesByRule(report, "PACING_TOTAL_DEVIATION").size());
    }
}
