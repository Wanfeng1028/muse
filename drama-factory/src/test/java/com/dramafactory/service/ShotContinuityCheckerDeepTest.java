package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * ShotContinuityChecker 深度单元测试。
 *
 * <p>纯单元测试：直接 new 被测对象，不依赖 Spring/DB/网络，无 mock。
 * 覆盖空列表、跨分镜一致性（景别/运镜/方向/对白承接）、场景跳跃（景别跳变）、
 * 时间线倒置（乱序 shotNo 排序）、单分镜边界、节奏配置边界、大批量性能（100 镜 5 秒内）、
 * 并发多线程启动、非法输入与中断传播。</p>
 */
class ShotContinuityCheckerDeepTest {

    private final ShotContinuityChecker checker = new ShotContinuityChecker();

    private Shot shot(Integer no, ShotSize size, CameraMove move, String desc, String dialogue, String videoPrompt) {
        Shot s = new Shot();
        s.setShotNo(no);
        s.setShotSize(size);
        s.setCameraMove(move);
        s.setDescription(desc);
        s.setDialogue(dialogue);
        s.setVideoPrompt(videoPrompt);
        return s;
    }

    private Shot shotWithDuration(Integer no, ShotSize size, CameraMove move, String desc,
                                  String dialogue, String videoPrompt, Integer durationSeconds) {
        Shot s = shot(no, size, move, desc, dialogue, videoPrompt);
        s.setDurationSeconds(durationSeconds);
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

    // ---------- 边界：空 / null ----------

    @Test
    void emptyAndNullListReturnZeroShotsCheckedAndNoIssues() {
        ShotContinuityChecker.ContinuityReport nullReport = checker.check(null);
        assertThat(nullReport.issues()).isEmpty();
        assertThat(nullReport.shotsChecked()).isZero();
        assertThat(nullReport.hasWarnings()).isFalse();

        ShotContinuityChecker.ContinuityReport emptyReport = checker.check(new ArrayList<>());
        assertThat(emptyReport.issues()).isEmpty();
        assertThat(emptyReport.shotsChecked()).isZero();

        ShotContinuityChecker.ContinuityReport emptyWithPacing =
                checker.check(new ArrayList<>(), ShotContinuityChecker.PacingConfig.defaults(60));
        assertThat(emptyWithPacing.issues()).isEmpty();
        assertThat(emptyWithPacing.shotsChecked()).isZero();
    }

    @Test
    void singleShotProducesNoContinuityWarning() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, "人物特写", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        assertThat(report.shotsChecked()).isEqualTo(1);
        assertThat(report.hasWarnings()).isFalse();
        assertThat(issuesByRule(report, "SHOT_SIZE_JUMP")).isEmpty();
        assertThat(issuesByRule(report, "AXIS_JUMP")).isEmpty();
        assertThat(issuesByRule(report, "DIALOGUE_HANDOFF")).isEmpty();
        assertThat(issuesByRule(report, "MONOTONOUS_RUN")).isEmpty();
    }

    // ---------- 跨分镜不一致：景别 / 运镜 / 方向 / 对白 ----------

    @Test
    void shotSizeJumpAcrossThreeRanksDetectedAsWarnWithSortedIssueOrder() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(2, ShotSize.YUAN_JING, CameraMove.GU_DING, "远景", "", ""));
        shots.add(shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, "特写", "", ""));
        shots.add(shot(4, ShotSize.YUAN_JING, CameraMove.GU_DING, "远景2", "", ""));
        shots.add(shot(3, ShotSize.TE_XIE, CameraMove.GU_DING, "特写2", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        List<ShotContinuityChecker.ContinuityIssue> hits = issuesByRule(report, "SHOT_SIZE_JUMP");
        assertThat(hits).hasSize(3);
        assertThat(hits).allMatch(i -> i.severity() == ShotContinuityChecker.Severity.WARN);
        assertThat(hits).extracting(ShotContinuityChecker.ContinuityIssue::shotNo)
                .containsExactly(2, 3, 4);
        assertThat(report.shotsChecked()).isEqualTo(4);
        // issue 列表整体按 shotNo 升序
        List<ShotContinuityChecker.ContinuityIssue> all = report.issues();
        for (int i = 0; i + 1 < all.size(); i++) {
            assertThat(all.get(i).shotNo()).isLessThanOrEqualTo(all.get(i + 1).shotNo());
        }
        // 景别交替变化，不触发单调
        assertThat(issuesByRule(report, "MONOTONOUS_RUN")).isEmpty();
    }

    @Test
    void extremeShotSizeJumpFromCloseUpToExtremeLongDetected() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, "特写", "", ""));
        shots.add(shot(2, ShotSize.YUAN_JING, CameraMove.GU_DING, "远景", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        List<ShotContinuityChecker.ContinuityIssue> hits = issuesByRule(report, "SHOT_SIZE_JUMP");
        assertThat(hits).hasSize(1);
        assertThat(hits.get(0).shotId()).isNull();
        assertThat(hits.get(0).severity()).isEqualTo(ShotContinuityChecker.Severity.WARN);
        assertThat(hits.get(0).message()).contains("特写").contains("远景");
    }

    @Test
    void repeatedCameraMoveAcrossThreeShotsDetectedAsInfo() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.TE_XIE, CameraMove.TUI, "a", "", ""));
        shots.add(shot(2, ShotSize.JIN_JING, CameraMove.TUI, "b", "", ""));
        shots.add(shot(3, ShotSize.ZHONG_JING, CameraMove.TUI, "c", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        List<ShotContinuityChecker.ContinuityIssue> hits = issuesByRule(report, "REPEATED_CAMERA_MOVE");
        assertThat(hits).hasSize(1);
        assertThat(hits.get(0).severity()).isEqualTo(ShotContinuityChecker.Severity.INFO);
        assertThat(hits.get(0).shotNo()).isEqualTo(3);
        assertThat(hits.get(0).message()).contains("推镜头");
    }

    @Test
    void axisJumpAcrossAdjacentShotsDetectedAsWarn() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "人物从左侧入画", "", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "人物朝右走去", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        List<ShotContinuityChecker.ContinuityIssue> hits = issuesByRule(report, "AXIS_JUMP");
        assertThat(hits).hasSize(1);
        assertThat(hits.get(0).severity()).isEqualTo(ShotContinuityChecker.Severity.WARN);
        assertThat(hits.get(0).shotNo()).isEqualTo(2);
    }

    @Test
    void dialogueHandoffQuestionWithoutResponseDetectedAsInfo() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "问话", "你准备好了吗？", ""));
        shots.add(shot(2, ShotSize.JIN_JING, CameraMove.GU_DING, "沉默镜头", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        List<ShotContinuityChecker.ContinuityIssue> hits = issuesByRule(report, "DIALOGUE_HANDOFF");
        assertThat(hits).hasSize(1);
        assertThat(hits.get(0).severity()).isEqualTo(ShotContinuityChecker.Severity.INFO);
    }

    // ---------- 时间线倒置（乱序输入 + 排序） ----------

    @Test
    void timelineInvertedInputIsSortedByShotNoAndReportIsAscending() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(5, ShotSize.ZHONG_JING, CameraMove.GU_DING, "e", "", ""));
        shots.add(shot(4, ShotSize.ZHONG_JING, CameraMove.GU_DING, "d", "", ""));
        shots.add(shot(3, ShotSize.ZHONG_JING, CameraMove.GU_DING, "c", "", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "b", "", ""));
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        assertThat(report.shotsChecked()).isEqualTo(5);
        List<ShotContinuityChecker.ContinuityIssue> all = report.issues();
        assertThat(all).isNotEmpty();
        for (int i = 0; i + 1 < all.size(); i++) {
            assertThat(all.get(i).shotNo()).isLessThanOrEqualTo(all.get(i + 1).shotNo());
        }
        // 5 镜同景别同运镜，触发 MONOTONOUS_RUN
        assertThat(issuesByRule(report, "MONOTONOUS_RUN")).hasSize(1);
    }

    @Test
    void nullShotNoEntriesSortedLastAndDoNotBreakReport() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(null, ShotSize.YUAN_JING, CameraMove.GU_DING, "no-no", "", ""));
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "", ""));
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "b", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        assertThat(report.shotsChecked()).isEqualTo(3);
        // null 排最后，前两个中景同运镜只有 2 镜，不触发单调
        assertThat(issuesByRule(report, "MONOTONOUS_RUN")).isEmpty();
    }

    // ---------- 节奏配置边界（R6） ----------

    @Test
    void pacingTargetDeviationTriggersWarnAndDurationBoundsTriggerWarn() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shotWithDuration(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "", "", 1));
        shots.add(shotWithDuration(2, ShotSize.JIN_JING, CameraMove.TUI, "b", "", "", 100));

        ShotContinuityChecker.PacingConfig pacing =
                new ShotContinuityChecker.PacingConfig(60, 2.0, 15.0, 15.0, 8.0, 0.6);

        ShotContinuityChecker.ContinuityReport report = checker.check(shots, pacing);

        List<ShotContinuityChecker.ContinuityIssue> bounds =
                issuesByRule(report, "SHOT_DURATION_OUT_OF_RANGE");
        assertThat(bounds).hasSize(2);
        assertThat(bounds).allMatch(i -> i.severity() == ShotContinuityChecker.Severity.WARN);

        List<ShotContinuityChecker.ContinuityIssue> deviation =
                issuesByRule(report, "PACING_TOTAL_DEVIATION");
        assertThat(deviation).hasSize(1);
        assertThat(deviation.get(0).severity()).isEqualTo(ShotContinuityChecker.Severity.WARN);
    }

    @Test
    void nullPacingSkipsR6AndStillRunsR7() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shotWithDuration(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "美丽的画面", "", "", 1));
        shots.add(shotWithDuration(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "b", "", "", 100));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots, null);

        assertThat(issuesByRule(report, "PACING_TOTAL_DEVIATION")).isEmpty();
        assertThat(issuesByRule(report, "SHOT_DURATION_OUT_OF_RANGE")).isEmpty();
        assertThat(issuesByRule(report, "GENERIC_PHRASE")).hasSize(1);
    }

    // ---------- 失败注入：非法输入 / 中断 ----------

    @Test
    void nullElementsInsideListAreSkippedWithoutThrowing() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, ShotSize.ZHONG_JING, CameraMove.GU_DING, "a", "", ""));
        shots.add(null);
        shots.add(shot(2, ShotSize.ZHONG_JING, CameraMove.GU_DING, "b", "", ""));

        ShotContinuityChecker.ContinuityReport report = checker.check(shots);

        assertThat(report.shotsChecked()).isEqualTo(2);
        assertThat(report.hasWarnings()).isFalse();
    }

    @Test
    void interruptionOfCallerThreadIsPropagatedNotSwallowed() {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger issuesCount = new AtomicInteger(-1);

        Thread worker = new Thread(() -> {
            try {
                List<Shot> shots = new ArrayList<>();
                for (int i = 1; i <= 50; i++) {
                    shots.add(shot(i, ShotSize.ZHONG_JING, CameraMove.GU_DING, "d" + i, "", ""));
                }
                started.countDown();
                release.await();
                ShotContinuityChecker.ContinuityReport report = checker.check(shots);
                issuesCount.set(report.issues().size());
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        });
        worker.start();
        try {
            assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();
            worker.interrupt();
            release.countDown();
            worker.join(2000);
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
        }

        assertThat(worker.isAlive()).isFalse();
        assertThat(worker.isInterrupted()).isTrue();
        assertThat(issuesCount.get()).isEqualTo(-1);
    }

    // ---------- 性能：100 镜 5 秒内 ----------

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void hundredShotsCheckedWithinFiveSeconds() {
        List<Shot> shots = new ArrayList<>();
        ShotSize[] sizes = ShotSize.values();
        CameraMove[] moves = CameraMove.values();
        for (int i = 1; i <= 100; i++) {
            Shot s = shot(i,
                    sizes[i % sizes.length],
                    moves[i % moves.length],
                    "画面细节 " + i,
                    i % 7 == 0 ? "问题" + i + "？" : "对白" + i,
                    "prompt " + i);
            s.setDurationSeconds(3 + (i % 5));
            shots.add(s);
        }

        ShotContinuityChecker.ContinuityReport report = checker.check(shots, ShotContinuityChecker.PacingConfig.defaults(300));

        assertThat(report.shotsChecked()).isEqualTo(100);
        assertThat(report.issues()).isNotNull();
        // 保证排序后 issue shotNo 非降序
        List<ShotContinuityChecker.ContinuityIssue> all = report.issues();
        for (int i = 0; i + 1 < all.size(); i++) {
            assertThat(all.get(i).shotNo()).isLessThanOrEqualTo(all.get(i + 1).shotNo());
        }
    }

    // ---------- 并发：CountDownLatch 多线程同时启动 ----------

    @Test
    void concurrentInvocationsFromMultipleThreadsProduceConsistentResults() throws Exception {
        final int threads = 8;
        final int shotsPerThread = 20;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch go = new CountDownLatch(1);
        List<ShotContinuityChecker.ContinuityReport> results =
                Collections.synchronizedList(new ArrayList<>());
        List<Throwable> failures = Collections.synchronizedList(new ArrayList<>());

        try {
            for (int t = 0; t < threads; t++) {
                final int base = t * 1000;
                pool.submit(() -> {
                    try {
                        List<Shot> shots = new ArrayList<>();
                        for (int i = 1; i <= shotsPerThread; i++) {
                            shots.add(shot(base + i,
                                    i % 2 == 0 ? ShotSize.TE_XIE : ShotSize.YUAN_JING,
                                    CameraMove.GU_DING,
                                    "并发场景 " + i, "", ""));
                        }
                        ready.countDown();
                        go.await();
                        ShotContinuityChecker.ContinuityReport r = checker.check(shots);
                        results.add(r);
                    } catch (Throwable ex) {
                        failures.add(ex);
                    }
                });
            }

            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            go.countDown();
            pool.shutdown();
            assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        } finally {
            pool.shutdownNow();
        }

        assertThat(failures).isEmpty();
        assertThat(results).hasSize(threads);
        for (ShotContinuityChecker.ContinuityReport r : results) {
            assertThat(r.shotsChecked()).isEqualTo(shotsPerThread);
            assertThat(r.hasWarnings()).isTrue();
            assertThat(issuesByRule(r, "SHOT_SIZE_JUMP")).hasSize(shotsPerThread - 1);
        }
    }

    // ---------- 报告 API：hasWarnings / 规则聚合 ----------

    @Test
    void reportHasWarningsTrueWhenWarnLevelIssueExistsAndFalseWhenOnlyInfo() {
        List<Shot> infoOnly = new ArrayList<>();
        infoOnly.add(shot(1, ShotSize.ZHONG_JING, CameraMove.TUI, "a", "去哪？", ""));
        infoOnly.add(shot(2, ShotSize.ZHONG_JING, CameraMove.LA, "b", "", ""));
        ShotContinuityChecker.ContinuityReport infoReport = checker.check(infoOnly);
        assertThat(infoReport.hasWarnings()).isFalse();
        assertThat(issuesByRule(infoReport, "PUSH_PULL")).hasSize(1);
        assertThat(issuesByRule(infoReport, "DIALOGUE_HANDOFF")).hasSize(1);

        List<Shot> warnOnly = new ArrayList<>();
        warnOnly.add(shot(1, ShotSize.TE_XIE, CameraMove.GU_DING, "特写", "", ""));
        warnOnly.add(shot(2, ShotSize.YUAN_JING, CameraMove.GU_DING, "远景", "", ""));
        ShotContinuityChecker.ContinuityReport warnReport = checker.check(warnOnly);
        assertThat(warnReport.hasWarnings()).isTrue();
    }

    @Test
    void pacingDefaultsFactoryProducesExpectedBoundaries() {
        ShotContinuityChecker.PacingConfig cfg = ShotContinuityChecker.PacingConfig.defaults(120);
        assertThat(cfg.targetDurationSeconds()).isEqualTo(120);
        assertThat(cfg.minShotSeconds()).isEqualTo(2.0);
        assertThat(cfg.maxShotSeconds()).isEqualTo(15.0);
        assertThat(cfg.warnDeviationPct()).isEqualTo(15.0);
        assertThat(cfg.infoDeviationPct()).isEqualTo(8.0);
        assertThat(cfg.shotSizeDominancePct()).isEqualTo(0.6);

        assertThat(ShotContinuityChecker.PacingConfig.defaults(120).equals(null)).isFalse();
        assertThat(ShotContinuityChecker.PacingConfig.defaults(120)
                .equals(ShotContinuityChecker.PacingConfig.defaults(120))).isTrue();
    }
}
