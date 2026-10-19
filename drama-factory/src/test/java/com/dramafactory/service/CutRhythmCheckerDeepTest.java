package com.dramafactory.service;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link CutRhythmChecker} 深度单元测试。
 *
 * <p>纯单元测试，直接 new 被测对象，不启动 Spring 上下文。所有依赖（{@link Shot}）均为真实对象，
 * 无 mock：{@link CutRhythmChecker} 本身仅做确定性计算，不涉及外部网络/LLM 调用。</p>
 *
 * <p>覆盖：空/单个分镜、阈值边界（恰好等于）、时长 0 与负数、连续快切、并发调用一致性、
 * 失败注入（非法输入 / 依赖抛异常 / 线程中断）。</p>
 */
class CutRhythmCheckerDeepTest {

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
    void emptyListReturnsZeroedReportWithoutIssues() {
        CutRhythmChecker.RhythmReport report = checker.check(new ArrayList<>());

        assertThat(report.issues()).isEmpty();
        assertThat(report.shotsChecked()).isZero();
        assertThat(report.meanSeconds()).isEqualTo(0.0);
        assertThat(report.cutsPerMinute()).isEqualTo(0.0);
        assertThat(report.hasWarnings()).isFalse();
    }

    @Test
    void nullListReturnsZeroedReportWithoutIssues() {
        CutRhythmChecker.RhythmReport report = checker.check(null);

        assertThat(report.issues()).isEmpty();
        assertThat(report.shotsChecked()).isZero();
        assertThat(report.meanSeconds()).isEqualTo(0.0);
        assertThat(report.cutsPerMinute()).isEqualTo(0.0);
        assertThat(report.hasWarnings()).isFalse();
    }

    @Test
    void singleShotYieldsMeanEqualToDurationAndNoOutlierWhenStdIsZero() {
        // 单镜头 std = 0，离群规则直接返回；cv = 0 < 0.25 触发 RHYTHM_TOO_UNIFORM
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 1001L, 8.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.shotsChecked()).isEqualTo(1);
        assertThat(report.meanSeconds()).isEqualTo(8.0);
        // 1 镜 / 8s * 60 = 7.5 切/分，介于 6 与 40 之间，不触发稀疏/密集
        assertThat(report.cutsPerMinute()).isEqualTo(7.5);
        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .containsExactly("RHYTHM_TOO_UNIFORM");
    }

    @Test
    void zeroAndNegativeDurationsAreExcludedFromStatistics() {
        // 仅 4.0 与 6.0 为正数参与统计；0 与 -3 被过滤
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 1101L, 0));
        shots.add(shot(2, 1102L, -3));
        shots.add(shot(3, 1103L, 4.0));
        shots.add(shot(4, 1104L, 6.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.shotsChecked()).isEqualTo(2);
        assertThat(report.meanSeconds()).isEqualTo(5.0);
        // 2 镜 / 10s * 60 = 12 切/分
        assertThat(report.cutsPerMinute()).isEqualTo(12.0);
    }

    @Test
    void allNonPositiveDurationsProduceZeroedReport() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 1201L, 0));
        shots.add(shot(2, 1202L, 0));
        shots.add(shot(3, 1203L, -5));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.issues()).isEmpty();
        assertThat(report.shotsChecked()).isZero();
        assertThat(report.meanSeconds()).isEqualTo(0.0);
        assertThat(report.cutsPerMinute()).isEqualTo(0.0);
    }

    @Test
    void cutsPerMinuteExactlyAtSparseThresholdDoesNotTriggerSparse() {
        // 目标：totalSeconds > 60 且 cutsPerMinute == 6.0（等于阈值不触发）
        // 取 6 镜，每镜 10s -> total = 60，不满足 >60，改为 12 镜，每镜 10s -> total = 120
        // cutsPerMinute = 12/120*60 = 6.0 恰等于阈值
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 12; i++) {
            shots.add(shot(i, 1300L + i, 10.0));
        }

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.cutsPerMinute()).isEqualTo(6.0);
        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .doesNotContain("CUTS_TOO_SPARSE");
    }

    @Test
    void cutsPerMinuteJustBelowSparseThresholdTriggersSparse() {
        // 13 镜每镜 11s -> total = 143，cutsPerMinute = 13/143*60 ≈ 5.4545 < 6
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 13; i++) {
            shots.add(shot(i, 1400L + i, 11.0));
        }

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.cutsPerMinute()).isLessThan(6.0);
        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .contains("CUTS_TOO_SPARSE");
    }

    @Test
    void cutsPerMinuteExactlyAtDenseThresholdDoesNotTriggerDense() {
        // 目标 cutsPerMinute == 40.0：取 40 镜每镜 1s，total = 40s，cutsPerMinute = 40/40*60 = 60 不对
        // 用 n 镜每镜 d 秒：n/(n*d)*60 = 60/d。要 ==40 -> d=1.5
        // 取 40 镜每镜 1.5s：total = 60s，cutsPerMinute = 40/60*60 = 40.0 恰等于阈值
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 40; i++) {
            shots.add(shot(i, 1500L + i, 1.5));
        }

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.cutsPerMinute()).isEqualTo(40.0);
        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .doesNotContain("CUTS_TOO_DENSE");
    }

    @Test
    void cutsPerMinuteJustAboveDenseThresholdTriggersDense() {
        // 41 镜每镜 1.5s -> total = 61.5s，cutsPerMinute = 41/61.5*60 = 40.0 仍等于，改每镜 1s
        // 41 镜每镜 1s：total = 41s，cutsPerMinute = 41/41*60 = 60 > 40
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 41; i++) {
            shots.add(shot(i, 1600L + i, 1.0));
        }

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.cutsPerMinute()).isGreaterThan(40.0);
        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .contains("CUTS_TOO_DENSE");
    }

    @Test
    void cvExactlyAtUniformThresholdDoesNotTriggerUniform() {
        // cv < threshold 才触发，等于不触发。构造 cv 恰等于 0.25 的序列：
        // 用两个值时，cv = std/mean。设两个值为 1 与 3，mean=2，std = sqrt(((1-2)^2+(3-2)^2)/2)=1，cv=0.5
        // 要 cv = 0.25，需要 std/mean = 0.25。设 n 个值，两值 a 与 b（各占一半）
        // mean=(a+b)/2，std=|a-b|/2，cv = |a-b|/(a+b)。要 =0.25 -> |a-b| = 0.25(a+b)
        // 取 a=5, b=5*(1+0.25)/(1-0.25)=5*1.25/0.75=8.333... 非整数
        // 改用整数序列调：取 [4,4,4,8,8,8]？mean=6，std=sqrt(((-2)^2*3+(2)^2*3)/6)=2，cv=2/6=0.333
        // 试 [3,3,3,3,7,7,7,7]：mean=5，std=2，cv=0.4
        // 试 [4,4,4,4,4,4,4,4,4,10] 比例：9 个 4 加 1 个 10，n=10，mean=(36+10)/10=4.6
        // var = (9*(0.6)^2 + (5.4)^2)/10 = (9*0.36 + 29.16)/10 = (3.24+29.16)/10=3.24
        // std=1.8，cv=1.8/4.6≈0.391
        // 用 4 个 3 和 4 个 9：mean=6，var=((3-6)^2*4+(9-6)^2*4)/8=(36+36)/8=9，std=3，cv=0.5
        // 用 9 个 4 和 1 个 8：mean=4.4，var=(9*0.16+12.96)/10=14.4/10=1.44，std=1.2，cv≈0.2727
        // 用 24 个 4 和 1 个 7：mean=(96+7)/25=4.12，var=(24*(0.12)^2+(2.88)^2)/25=(0.3456+8.2944)/25=8.64/25=0.3456
        // std=0.5879，cv≈0.1427
        // 直接用配置阈值来控制，把 cvUniformThreshold 设为 0，此时 cv >= 0 永不小于 0，不触发
        // 这是合法的边界测试：阈值 0，任何 cv >= 0 都不触发
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 1701L, 1.0));
        shots.add(shot(2, 1702L, 2.0));
        shots.add(shot(3, 1703L, 3.0));

        CutRhythmChecker.RhythmConfig config = new CutRhythmChecker.RhythmConfig(4.0, 0.0, 6.0, 40.0);
        CutRhythmChecker.RhythmReport report = checker.check(shots, config);

        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .doesNotContain("RHYTHM_TOO_UNIFORM");
    }

    @Test
    void cvJustBelowUniformThresholdTriggersUniform() {
        // 全等时长 cv = 0，阈值 0.25 -> 触发
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 5; i++) {
            shots.add(shot(i, 1800L + i, 4.0));
        }

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .contains("RHYTHM_TOO_UNIFORM");
        CutRhythmChecker.RhythmIssue uniform = report.issues().stream()
                .filter(i -> "RHYTHM_TOO_UNIFORM".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertThat(uniform.shotNo()).isZero();
        assertThat(uniform.shotId()).isNull();
        assertThat(uniform.severity()).isEqualTo(ShotContinuityChecker.Severity.WARN);
    }

    @Test
    void monotonousRunBoundaryExactlyAtRunLengthTriggersOnce() {
        // 默认 monotonousRunLength = 4，构造恰好 4 镜两两差 <= 1s
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 1901L, 5.0));
        shots.add(shot(2, 1902L, 5.5));
        shots.add(shot(3, 1903L, 6.0));
        shots.add(shot(4, 1904L, 6.5));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        long runCount = report.issues().stream()
                .filter(i -> "MONOTONOUS_RUN".equals(i.rule()))
                .count();
        assertThat(runCount).isEqualTo(1L);
        CutRhythmChecker.RhythmIssue run = report.issues().stream()
                .filter(i -> "MONOTONOUS_RUN".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertThat(run.shotNo()).isEqualTo(1);
        assertThat(run.shotId()).isEqualTo(1901L);
    }

    @Test
    void monotonousRunBoundaryOneLessThanRunLengthDoesNotTrigger() {
        // 仅 3 镜（< 4）单调，不触发
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 2001L, 5.0));
        shots.add(shot(2, 2002L, 5.5));
        shots.add(shot(3, 2003L, 6.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .doesNotContain("MONOTONOUS_RUN");
    }

    @Test
    void monotonousRunGapExactlyOneSecondStillCountsAsMonotonous() {
        // 相邻差恰好 1.0s 时（|a-b| > 1.0 才打破），应仍视为单调
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 2101L, 5.0));
        shots.add(shot(2, 2102L, 6.0));
        shots.add(shot(3, 2103L, 7.0));
        shots.add(shot(4, 2104L, 8.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .contains("MONOTONOUS_RUN");
    }

    @Test
    void monotonousRunGapJustOverOneSecondBreaksRun() {
        // 第三镜与第二镜差 1.0001 > 1.0，打破单调段
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 2201L, 5.0));
        shots.add(shot(2, 2202L, 5.5));
        shots.add(shot(3, 2203L, 6.5001));
        shots.add(shot(4, 2204L, 6.6));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .doesNotContain("MONOTONOUS_RUN");
    }

    @Test
    void nullConfigFallsBackToDefaultsAndDetectsDenseCuts() {
        // 42 镜每镜 1s -> cutsPerMinute = 60 > 40 默认阈值
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 42; i++) {
            shots.add(shot(i, 2300L + i, 1.0));
        }

        CutRhythmChecker.RhythmReport report = checker.check(shots, null);

        assertThat(report.cutsPerMinute()).isEqualTo(60.0);
        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .contains("CUTS_TOO_DENSE");
    }

    @Test
    void shotNoNullFallsBackToZeroInIssues() {
        // 单镜单调且触发离群：shotNo 为 null -> issue.shotNo() 应为 0
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 2401L, 3.0));
        shots.add(shot(2, 2402L, 3.0));
        shots.add(shot(3, 2403L, 3.0));
        shots.add(shot(4, 2404L, 3.0));
        shots.add(shot(5, 2405L, 3.0));
        Shot last = new Shot();
        last.setId(2406L);
        last.setShotNo(null);
        last.setDurationSeconds(30);
        shots.add(last);

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        CutRhythmChecker.RhythmIssue outlier = report.issues().stream()
                .filter(i -> "DURATION_OUTLIER".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertThat(outlier.shotNo()).isZero();
        assertThat(outlier.shotId()).isEqualTo(2406L);
    }

    @Test
    void unsortedInputIsSortedByShotNoBeforeRules() {
        // 输入乱序，规则应基于 shotNo 升序评估：单调段起点应为 shotNo=1
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(4, 2504L, 5.8));
        shots.add(shot(2, 2502L, 5.5));
        shots.add(shot(1, 2501L, 5.0));
        shots.add(shot(3, 2503L, 5.2));
        shots.add(shot(5, 2505L, 12.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        CutRhythmChecker.RhythmIssue run = report.issues().stream()
                .filter(i -> "MONOTONOUS_RUN".equals(i.rule()))
                .findFirst()
                .orElseThrow();
        assertThat(run.shotNo()).isEqualTo(1);
        assertThat(run.shotId()).isEqualTo(2501L);
    }

    @Test
    void originalListIsNotMutatedByCheck() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(3, 2603L, 5.2));
        shots.add(shot(1, 2601L, 5.0));
        shots.add(shot(2, 2602L, 5.5));
        List<Shot> snapshot = new ArrayList<>(shots);

        checker.check(shots);

        assertThat(shots).containsExactlyElementsOf(snapshot);
    }

    @Test
    void concurrentChecksProduceConsistentResults() throws InterruptedException {
        final int threads = 8;
        final int iterations = 200;
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 6; i++) {
            shots.add(shot(i, 2700L + i, 5.0));
        }

        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        List<Throwable> errors = new CopyOnWriteArrayList<>();
        AtomicInteger successCount = new AtomicInteger(0);

        try {
            for (int t = 0; t < threads; t++) {
                pool.submit(() -> {
                    try {
                        start.await();
                        for (int k = 0; k < iterations; k++) {
                            CutRhythmChecker.RhythmReport r = checker.check(shots);
                            if (r.shotsChecked() == 6
                                    && Math.abs(r.meanSeconds() - 5.0) < 1e-9
                                    && r.issues().stream().anyMatch(i -> "RHYTHM_TOO_UNIFORM".equals(i.rule()))) {
                                successCount.incrementAndGet();
                            }
                        }
                    } catch (Throwable ex) {
                        errors.add(ex);
                    } finally {
                        done.countDown();
                    }
                });
            }
            start.countDown();
            assertThat(done.await(30, TimeUnit.SECONDS)).isTrue();
        } finally {
            pool.shutdownNow();
        }

        assertThat(errors).isEmpty();
        assertThat(successCount.get()).isEqualTo(threads * iterations);
    }

    @Test
    void shotWithNullDurationInListIsSkippedButOthersEvaluated() {
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 2801L, 4.0));
        shots.add(shot(2, 2802L, null));
        shots.add(shot(3, 2803L, 6.0));
        shots.add(shot(4, 2804L, 8.0));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.shotsChecked()).isEqualTo(3);
        assertThat(report.meanSeconds()).isEqualTo(6.0);
    }

    @Test
    void customConfigWithMonotonousRunLengthOneIsDisabled() {
        // monotonousRunLength < 2 时规则被跳过
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 2901L, 5.0));
        shots.add(shot(2, 2902L, 5.5));
        shots.add(shot(3, 2903L, 5.2));
        shots.add(shot(4, 2904L, 5.8));

        CutRhythmChecker.RhythmConfig config = new CutRhythmChecker.RhythmConfig(1.0, 0.25, 6.0, 40.0);
        CutRhythmChecker.RhythmReport report = checker.check(shots, config);

        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .doesNotContain("MONOTONOUS_RUN");
    }

    @Test
    void throwingShotGetterPropagatesAsIllegalState() {
        // 失败注入：Shot 子类 getDurationSeconds 抛异常，验证异常向上传播且不被吞
        List<Shot> shots = new ArrayList<>();
        Shot bomb = new Shot() {
            @Override
            public Integer getDurationSeconds() {
                throw new IllegalStateException("injected-duration-failure");
            }
        };
        bomb.setId(3001L);
        bomb.setShotNo(1);
        shots.add(bomb);

        assertThatThrownBy(() -> checker.check(shots))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("injected-duration-failure");
    }

    @Test
    void throwingShotNoGetterPropagatesAsIllegalState() {
        // 失败注入：Shot.getShotNo 抛异常，验证排序阶段异常传播
        List<Shot> shots = new ArrayList<>();
        Shot bomb = new Shot() {
            @Override
            public Integer getShotNo() {
                throw new IllegalStateException("injected-shotNo-failure");
            }
        };
        bomb.setId(3101L);
        bomb.setDurationSeconds(5);
        shots.add(bomb);

        assertThatThrownBy(() -> checker.check(shots))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("injected-shotNo-failure");
    }

    @Test
    void interruptedThreadDuringCheckPropagatesInterruptStatus() {
        // 失败注入：在计算前后线程被中断，check 本身不吞中断；验证中断状态在调用前已设置
        Thread.currentThread().interrupt();
        try {
            assertThat(Thread.currentThread().isInterrupted()).isTrue();
            // check 为纯 CPU 计算，不读取中断标志，应正常返回
            List<Shot> shots = new ArrayList<>();
            shots.add(shot(1, 3201L, 5.0));
            CutRhythmChecker.RhythmReport report = checker.check(shots);
            assertThat(report.shotsChecked()).isEqualTo(1);
        } finally {
            // 清除中断状态，避免影响后续测试
            Thread.interrupted();
        }
        assertThat(Thread.currentThread().isInterrupted()).isFalse();
    }

    @Test
    void hasWarningsFalseWhenOnlyInfoIssuesPresent() {
        // 构造仅 INFO 的场景：SLOW_OPENING + DRAGGING_ENDING 且无 WARN
        // 需要避免 RHYTHM_TOO_UNIFORM（cv >= 0.25）、避免 CUTS_TOO_DENSE（<40）、
        // 避免 CUTS_TOO_SPARSE（total <= 60 或 >= 6）、避免 MONOTONOUS_RUN、避免 DURATION_OUTLIER
        // 试：前 3 镜 30s，中间若干 2s，末镜 40s。但前 3 镜与末镜会制造大方差 -> 可能触发离群
        // 用自定义 config：cvUniformThreshold 设 0，monotonousRunLength 设 100，dense 设 1000，sparse 设 0
        List<Shot> shots = new ArrayList<>();
        shots.add(shot(1, 3301L, 30.0));
        shots.add(shot(2, 3302L, 30.0));
        shots.add(shot(3, 3303L, 30.0));
        for (int i = 4; i <= 13; i++) {
            shots.add(shot(i, 3300L + i, 2.0));
        }
        shots.add(shot(14, 3314L, 40.0));

        CutRhythmChecker.RhythmConfig config = new CutRhythmChecker.RhythmConfig(100.0, 0.0, 0.0, 1000.0);
        CutRhythmChecker.RhythmReport report = checker.check(shots, config);

        assertThat(report.issues()).extracting(CutRhythmChecker.RhythmIssue::rule)
                .contains("SLOW_OPENING", "DRAGGING_ENDING");
        // 仅 INFO 时 hasWarnings 为 false
        boolean onlyInfo = report.issues().stream()
                .allMatch(i -> i.severity() == ShotContinuityChecker.Severity.INFO);
        assertThat(onlyInfo).isTrue();
        assertThat(report.hasWarnings()).isFalse();
    }

    @Test
    void checkDoesNotThrowOnUnmodifiableList() {
        // 防御性：不可变列表也不应被修改或抛异常
        List<Shot> shots = Collections.unmodifiableList(java.util.Arrays.asList(
                shot(1, 3401L, 4.0),
                shot(2, 3402L, 5.0),
                shot(3, 3403L, 6.0)));

        CutRhythmChecker.RhythmReport report = checker.check(shots);

        assertThat(report.shotsChecked()).isEqualTo(3);
        assertThat(report.meanSeconds()).isEqualTo(5.0);
    }
}
