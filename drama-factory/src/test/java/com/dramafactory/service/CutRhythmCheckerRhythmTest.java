package com.dramafactory.service;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class CutRhythmCheckerRhythmTest {

    private final CutRhythmChecker checker = new CutRhythmChecker();

    private List<Shot> shots(Integer... durations) {
        List<Shot> list = new ArrayList<>();
        for (int i = 0; i < durations.length; i++) {
            Shot shot = new Shot();
            shot.setShotNo(i + 1);
            shot.setDurationSeconds(durations[i]);
            list.add(shot);
        }
        return list;
    }

    @Test
    void durationOutlierLowerBoundFires() {
        List<Shot> shots = shots(20, 20, 20, 20, 20, 2);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        var issues = report.issues().stream()
                .filter(i -> "DURATION_OUTLIER".equals(i.rule()))
                .toList();
        assertEquals(1, issues.size());
        assertEquals(6, issues.get(0).shotNo());
        assertEquals(ShotContinuityChecker.Severity.WARN, issues.get(0).severity());
    }

    @Test
    void durationOutlierExactlyOnBoundaryDoesNotFire() {
        List<Shot> shots = shots(2, 2, 2, 2, 20);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        boolean exists = report.issues().stream()
                .anyMatch(i -> "DURATION_OUTLIER".equals(i.rule()));
        assertFalse(exists);
    }

    @Test
    void draggingEndingExactlyTwiceMeanDoesNotFire() {
        List<Shot> shots = shots(6, 6, 6, 18);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        boolean exists = report.issues().stream()
                .anyMatch(i -> "DRAGGING_ENDING".equals(i.rule()));
        assertFalse(exists);
    }

    @Test
    void draggingEndingJustOverTwiceMeanFires() {
        List<Shot> shots = shots(6, 6, 6, 19);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        var issues = report.issues().stream()
                .filter(i -> "DRAGGING_ENDING".equals(i.rule()))
                .toList();
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, issues.get(0).severity());
    }

    @Test
    void slowOpeningExactlyOnePointFiveTimesMeanDoesNotFire() {
        List<Shot> shots = shots(9, 9, 9, 3, 3, 3);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        boolean exists = report.issues().stream()
                .anyMatch(i -> "SLOW_OPENING".equals(i.rule()));
        assertFalse(exists);
    }

    @Test
    void slowOpeningJustOverThresholdFires() {
        List<Shot> shots = shots(12, 12, 12, 3, 3, 3);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        var issues = report.issues().stream()
                .filter(i -> "SLOW_OPENING".equals(i.rule()))
                .toList();
        assertEquals(1, issues.size());
        assertEquals(ShotContinuityChecker.Severity.INFO, issues.get(0).severity());
    }

    @Test
    void onlyInfoIssuesMeansNoWarnings() {
        List<Shot> shots = shots(12, 12, 12, 3, 3, 3);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        assertEquals(1, report.issues().size());
        assertFalse(report.hasWarnings());
    }

    @Test
    void customSparseThresholdFiresWithCustomConfig() {
        List<Shot> shots = shots(10, 10, 10, 10, 10, 10, 10);
        CutRhythmChecker.RhythmConfig config = new CutRhythmChecker.RhythmConfig(4.0, 0.25, 100.0, 40.0);
        CutRhythmChecker.RhythmReport report = checker.check(shots, config);
        var issues = report.issues().stream()
                .filter(i -> "CUTS_TOO_SPARSE".equals(i.rule()))
                .toList();
        assertEquals(1, issues.size());
    }

    @Test
    void twoSeparateMonotonousRunsProduceTwoIssues() {
        List<Shot> shots = shots(5, 5, 5, 5, 9, 9, 9, 9);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        var issues = report.issues().stream()
                .filter(i -> "MONOTONOUS_RUN".equals(i.rule()))
                .toList();
        assertEquals(2, issues.size());
    }

    @Test
    void runLengthBelowTwoDisablesMonotonousCheck() {
        List<Shot> shots = shots(5, 5, 5, 5);
        CutRhythmChecker.RhythmConfig config = new CutRhythmChecker.RhythmConfig(1.0, 0.25, 6.0, 40.0);
        CutRhythmChecker.RhythmReport report = checker.check(shots, config);
        boolean exists = report.issues().stream()
                .anyMatch(i -> "MONOTONOUS_RUN".equals(i.rule()));
        assertFalse(exists);
    }

    @Test
    void configurableRunLengthTwo() {
        List<Shot> shots = shots(5, 5, 9);
        CutRhythmChecker.RhythmConfig config = new CutRhythmChecker.RhythmConfig(2.0, 0.25, 6.0, 40.0);
        CutRhythmChecker.RhythmReport report = checker.check(shots, config);
        var issues = report.issues().stream()
                .filter(i -> "MONOTONOUS_RUN".equals(i.rule()))
                .toList();
        assertEquals(1, issues.size());
    }

    @Test
    void statisticsMeanAndCutsPerMinute() {
        List<Shot> shots = shots(6, 12);
        CutRhythmChecker.RhythmReport report = checker.check(shots);
        assertEquals(2, report.shotsChecked());
        assertEquals(9.0, report.meanSeconds(), 1e-9);
        assertEquals(20.0 / 3.0, report.cutsPerMinute(), 1e-9);
    }
}