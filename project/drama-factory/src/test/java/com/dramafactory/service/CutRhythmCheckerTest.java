package com.dramafactory.service;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@link CutRhythmChecker} 单元测试。
 */
class CutRhythmCheckerTest {

    private final CutRhythmChecker checker = new CutRhythmChecker();

    /**
     * 构造一个带镜号与 ID 的分镜。
     *
     * @param shotNo          镜号
     * @param id              分镜 ID
     * @param durationSeconds 时长（秒），可为 null
     * @return 分镜对象
     */
    private Shot shot(int shotNo, long id, Number durationSeconds) {
        Shot s = new Shot();
        s.setId(id);
        s.setShotNo(shotNo);
        s.setDurationSeconds(durationSeconds == null ? null : durationSeconds.intValue());
        return s;
    }

    @Test
    void durationOutlierDetected() {
        // 时长为 [3,3,3,3,3,30]，均值 = 7.5，总体标准差 = sqrt( ((-4.5)^2*5 + (22.5)^2 ) / 6 ) = sqrt( (101.25 + 506.25)/6 ) = sqrt(101.25) ≈ 10.06
        // 上界 = 7.5 + 2*10.06 = 27.62，30 > 27.62 属离群；其余 3 落在下界 7.5-20.12=-12.62 之内
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 101L, 3.0));
        shots.add(shot(2, 102L, 3.0));
        shots.add(shot(3, 103L, 3.0));
        shots.add(shot(4, 104L, 3.0));
        shots.add(shot(5, 105L, 3.0));
        shots.add(shot(6, 106L, 30.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        long outlierCount = report.issues().stream()
                .filter(i -> "DURATION_OUTLIER".equals(i.rule()))
                .count();
        assertEquals(1L, outlierCount);
        assertEquals(6, report.shotsChecked());
        assertEquals(7.5, report.meanSeconds(), 1e-9);

        CutRhythmChecker.RhythmIssue outlier = report.issues().stream()
                .filter(i -> "DURATION_OUTLIER".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertEquals(6, outlier.shotNo());
        assertEquals(106L, outlier.shotId());
        assertEquals(ShotContinuityChecker.Severity.WARN, outlier.severity());
    }

    @Test
    void uniformRhythmWarns() {
        // 所有时长都是 5s，标准差为 0，变异系数 0 < 0.25
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 6; i++) {
            shots.add(shot(i, 200L + i, 5.0));
        }

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        long uniformCount = report.issues().stream()
                .filter(i -> "RHYTHM_TOO_UNIFORM".equals(i.rule()))
                .count();
        assertEquals(1L, uniformCount);

        CutRhythmChecker.RhythmIssue issue = report.issues().stream()
                .filter(i -> "RHYTHM_TOO_UNIFORM".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertEquals(0, issue.shotNo());
        assertEquals(null, issue.shotId());
        assertEquals(ShotContinuityChecker.Severity.WARN, issue.severity());
        assertTrue(report.hasWarnings());
    }

    @Test
    void cutsTooSparseDetected() {
        // 4 个镜头，每个 30s，总时长 120s > 60s，cutsPerMinute = 4/120*60 = 2.0 < 6.0
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 301L, 30.0));
        shots.add(shot(2, 302L, 30.0));
        shots.add(shot(3, 303L, 30.0));
        shots.add(shot(4, 304L, 30.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertEquals(2.0, report.cutsPerMinute(), 1e-9);
        long sparseCount = report.issues().stream()
                .filter(i -> "CUTS_TOO_SPARSE".equals(i.rule()))
                .count();
        assertEquals(1L, sparseCount);
        long denseCount = report.issues().stream()
                .filter(i -> "CUTS_TOO_DENSE".equals(i.rule()))
                .count();
        assertEquals(0L, denseCount);
    }

    @Test
    void cutsTooDenseDetected() {
        // 42 个镜头，每个 1s，总时长 42s，cutsPerMinute = 42/42*60 = 60.0 > 40.0
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 42; i++) {
            shots.add(shot(i, 400L + i, 1.0));
        }

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertEquals(60.0, report.cutsPerMinute(), 1e-9);
        long denseCount = report.issues().stream()
                .filter(i -> "CUTS_TOO_DENSE".equals(i.rule()))
                .count();
        assertEquals(1L, denseCount);
        long sparseCount = report.issues().stream()
                .filter(i -> "CUTS_TOO_SPARSE".equals(i.rule()))
                .count();
        assertEquals(0L, sparseCount);
    }

    @Test
    void monotonousRunDetected() {
        // 前 4 镜时长 5.0 / 5.5 / 5.2 / 5.8，两两差不超过 1s，构成单调段
        // 第 5 镜 12s 打破单调
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 501L, 5.0));
        shots.add(shot(2, 502L, 5.5));
        shots.add(shot(3, 503L, 5.2));
        shots.add(shot(4, 504L, 5.8));
        shots.add(shot(5, 505L, 12.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        long runCount = report.issues().stream()
                .filter(i -> "MONOTONOUS_RUN".equals(i.rule()))
                .count();
        assertEquals(1L, runCount);

        CutRhythmChecker.RhythmIssue issue = report.issues().stream()
                .filter(i -> "MONOTONOUS_RUN".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertEquals(1, issue.shotNo());
        assertEquals(501L, issue.shotId());
        assertEquals(ShotContinuityChecker.Severity.WARN, issue.severity());
    }

    @Test
    void emptyListDoesNotThrow() {
        CutRhythmChecker.RhythmReport report = checker.check(new ArrayList<>());

        assertTrue(report.issues().isEmpty());
        assertEquals(0, report.shotsChecked());
        assertEquals(0.0, report.meanSeconds(), 1e-9);
        assertEquals(0.0, report.cutsPerMinute(), 1e-9);
        assertFalse(report.hasWarnings());
    }

    @Test
    void nullInputDoesNotThrow() {
        CutRhythmChecker.RhythmReport report = checker.check(null);

        assertTrue(report.issues().isEmpty());
        assertEquals(0, report.shotsChecked());
        assertEquals(0.0, report.meanSeconds(), 1e-9);
        assertEquals(0.0, report.cutsPerMinute(), 1e-9);
        assertFalse(report.hasWarnings());
    }

    @Test
    void nullDurationsSkipped() {
        // 一个 null 时长镜头被跳过，仅统计另外 3 个有效镜头
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 601L, 4.0));
        shots.add(shot(2, 602L, null));
        shots.add(shot(3, 603L, 6.0));
        shots.add(shot(4, 604L, 8.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertEquals(3, report.shotsChecked());
        assertEquals(6.0, report.meanSeconds(), 1e-9);
    }

    @Test
    void slowOpeningAndDraggingEndingAreInfo() {
        // 前 3 镜平均 = (12+12+12)/3 = 12，整体均值 = (12+12+12+2+2+30)/6 = 70/6 ≈ 11.667
        // 12 > 11.667 * 1.5 = 17.5 不成立 -> 调整时长
        // 重新设计：前 3 镜 20s，中间 2s，末镜 30s
        // 均值 = (20+20+20+2+2+30)/6 = 94/6 ≈ 15.667
        // 前 3 镜均值 = 20 > 15.667 * 1.5 = 23.5 不成立
        // 再次设计：前 3 镜 30s，其余 2s，末镜 40s
        // 均值 = (30+30+30+2+2+40)/6 = 134/6 ≈ 22.333
        // 前 3 镜均值 = 30 > 22.333 * 1.5 = 33.5 不成立
        // 使用更多镜头：前 3 镜 30s，其余 10 个 2s，末镜 40s
        // 总镜头 = 3 + 10 + 1 = 14；sum = 90 + 20 + 40 = 150；均值 = 150/14 ≈ 10.714
        // 前 3 镜均值 30 > 10.714 * 1.5 = 16.07 成立 -> SLOW_OPENING
        // 末镜 40 > 10.714 * 2 = 21.43 成立 -> DRAGGING_ENDING
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 701L, 30.0));
        shots.add(shot(2, 702L, 30.0));
        shots.add(shot(3, 703L, 30.0));
        for (int i = 4; i <= 13; i++) {
            shots.add(shot(i, 700L + i, 2.0));
        }
        shots.add(shot(14, 714L, 40.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        CutRhythmChecker.RhythmIssue slowOpening = report.issues().stream()
                .filter(i -> "SLOW_OPENING".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertEquals(ShotContinuityChecker.Severity.INFO, slowOpening.severity());
        assertEquals(0, slowOpening.shotNo());

        CutRhythmChecker.RhythmIssue draggingEnding = report.issues().stream()
                .filter(i -> "DRAGGING_ENDING".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertEquals(ShotContinuityChecker.Severity.INFO, draggingEnding.severity());
        assertEquals(14, draggingEnding.shotNo());
        assertEquals(714L, draggingEnding.shotId());
    }
}
