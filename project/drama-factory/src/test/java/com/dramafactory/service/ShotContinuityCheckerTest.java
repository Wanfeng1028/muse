package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * ShotContinuityChecker 纯单测：不依赖 Spring/DB/网络。
 */
class ShotContinuityCheckerTest {

    private final ShotContinuityChecker checker = new ShotContinuityChecker();

    private Shot shot(int no, ShotSize size, CameraMove move, String desc, String dialogue, String videoPrompt) {
        Shot s = new Shot();
        s.setShotNo(no);
        s.setShotSize(size);
        s.setCameraMove(move);
        s.setDescription(desc);
        s.setDialogue(dialogue);
        s.setVideoPrompt(videoPrompt);
        return s;
    }

    private List<ShotContinuityChecker.ContinuityIssue> issuesByRule(
            ShotContinuityChecker.ContinuityReport report, String rule) {
        List<ShotContinuityChecker.ContinuityIssue> result = new ArrayList<>();
        for (ShotContinuityChecker.ContinuityIssue i : report.issues()) {
            if (rule.equals(i.rule())) {
                result.add(i);
            }
        }
        return result;
    }

    @Test
    void nullAndEmpty() {
        assertEquals(0, checker.check(null).issues().size());
        assertEquals(0, checker.check(null).shotsChecked());
        assertEquals(0, checker.check(new ArrayList<>()).issues().size());
        assertEquals(0, checker.check(new ArrayList<>()).shotsChecked());
    }

    @Test
    void shotSizeJumpWarn() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, "a", "", ""));
        shots.add(shot(2, ShotSize.YUAN_JING, CameraMove.GU_DING, "b", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        List<ShotContinuityChecker.ContinuityIssue> hit = issuesByRule(report, "SHOT_SIZE_JUMP");
        assertEquals(1, hit.size());
        assertEquals(ShotContinuityChecker.Severity.WARN, hit.get(0).severity());
    }

    @Test
    void shotSizeCloseNoIssue() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "", ""));
        shots.add(shot(2, ShotSize.JIN_JING, CameraMove.GU_DING, "b", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        assertEquals(0, report.issues().size());
    }

    @Test
    void monotonousRunThreeInfo() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "b", "", ""));
        shots.add(shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, "c", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        List<ShotContinuityChecker.ContinuityIssue> hit = issuesByRule(report, "MONOTONOUS_RUN");
        assertEquals(1, hit.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, hit.get(0).severity());
    }

    @Test
    void monotonousRunTwoNoIssue() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "b", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        assertEquals(0, issuesByRule(report, "MONOTONOUS_RUN").size());
    }

    @Test
    void pushPullInfo() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.TUI, "a", "", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.LA, "b", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        List<ShotContinuityChecker.ContinuityIssue> hit = issuesByRule(report, "PUSH_PULL");
        assertEquals(1, hit.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, hit.get(0).severity());
    }

    @Test
    void axisJumpWarn() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "人物从左侧入画", "", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "人物朝右走去", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        List<ShotContinuityChecker.ContinuityIssue> hit = issuesByRule(report, "AXIS_JUMP");
        assertEquals(1, hit.size());
        assertEquals(ShotContinuityChecker.Severity.WARN, hit.get(0).severity());
    }

    @Test
    void axisUnknownNoIssue() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "人物入画", "", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "人物走去", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        assertEquals(0, issuesByRule(report, "AXIS_JUMP").size());
    }

    @Test
    void dialogueHandoffInfo() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "你去哪？", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "b", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        List<ShotContinuityChecker.ContinuityIssue> hit = issuesByRule(report, "DIALOGUE_HANDOFF");
        assertEquals(1, hit.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, hit.get(0).severity());
    }

    @Test
    void dialogueHandoffWithResponseNoIssue() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "你去哪？", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "他点头", "", ""));
        ShotContinuityChecker.ContinuityReport report = checker.check(shots);
        assertEquals(0, issuesByRule(report, "DIALOGUE_HANDOFF").size());
    }

    @Test
    void hasWarnings() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, "a", "", ""));
        shots.add(shot(2, ShotSize.YUAN_JING, CameraMove.GU_DING, "b", "", ""));
        assertTrue(checker.check(shots).hasWarnings());
    }
}
