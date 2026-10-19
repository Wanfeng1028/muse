package com.dramafactory.service;

import com.dramafactory.model.Shot;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * 成片节奏校验器。
 *
 * <p>设计思想借鉴 OpenMontage 的 verify_scene_pacing / slideshow_risk 节奏校验思路，
 * 但全部规则均为本仓库确定性 Java 独立实现：仅依赖分镜时长与镜号，不做任何随机或
 * 外部调用，便于单测与结果复现。</p>
 *
 * <p>严重级别复用 {@link ShotContinuityChecker.Severity}（WARN / INFO），不重复定义枚举。</p>
 */
@Service
public class CutRhythmChecker {

    /**
     * 单条节奏问题。
     *
     * @param shotNo     镜号，0 表示整体性（非单镜）问题
     * @param shotId     分镜 ID，整体性问题为 null
     * @param rule       规则名
     * @param severity   严重级别
     * @param message    问题描述
     * @param suggestion 建议
     */
    public record RhythmIssue(int shotNo, Long shotId, String rule, ShotContinuityChecker.Severity severity,
                              String message, String suggestion) {
    }

    /**
     * 节奏校验报告。
     *
     * @param issues         问题列表
     * @param shotsChecked   参与统计的分镜数（仅统计时长非空的镜头）
     * @param meanSeconds    参与统计镜头的平均时长（秒），无有效镜头时为 0
     * @param cutsPerMinute  每分钟切镜数（= 有效镜头数 / 总时长 * 60），无有效镜头时为 0
     */
    public record RhythmReport(List<RhythmIssue> issues, int shotsChecked, double meanSeconds, double cutsPerMinute) {

        /**
         * 是否包含警告级别的问题。
         *
         * @return 含 WARN 返回 true
         */
        public boolean hasWarnings() {
            return issues.stream().anyMatch(i -> i.severity() == ShotContinuityChecker.Severity.WARN);
        }
    }

    /**
     * 节奏校验配置。
     *
     * @param monotonousRunLength    连续单调段的最小镜头数（两两时长差不超过 1s）
     * @param cvUniformThreshold     变异系数低于该值判定节奏过于均匀
     * @param sparseCutsPerMinute    每分钟切镜数低于该值判定转场过稀
     * @param denseCutsPerMinute     每分钟切镜数高于该值判定转场过密
     */
    public record RhythmConfig(double monotonousRunLength,
                               double cvUniformThreshold,
                               double sparseCutsPerMinute,
                               double denseCutsPerMinute) {

        /**
         * 默认配置：连续 4 镜单调、变异系数低于 0.25 判均匀、每分钟低于 6 切过稀、高于 40 切过密。
         *
         * @return 默认配置
         */
        public static RhythmConfig defaults() {
            return new RhythmConfig(4.0, 0.25, 6.0, 40.0);
        }
    }

    /**
     * 使用默认配置做节奏校验。
     *
     * @param shots 分镜列表，可为 null 或空
     * @return 节奏报告
     */
    public RhythmReport check(List<Shot> shots) {
        return check(shots, RhythmConfig.defaults());
    }

    /**
     * 按给定配置做节奏校验。
     *
     * <p>仅统计 durationSeconds 非空的镜头；空列表、全空时长、null 输入均返回空问题报告，
     * 不抛异常。</p>
     *
     * @param shots  分镜列表，可为 null 或空
     * @param config 节奏校验配置，null 时使用默认配置
     * @return 节奏报告
     */
    public RhythmReport check(List<Shot> shots, RhythmConfig config) {
        RhythmConfig cfg = config == null ? RhythmConfig.defaults() : config;

        if (shots == null || shots.isEmpty()) {
            return new RhythmReport(new ArrayList<>(), 0, 0.0, 0.0);
        }

        // 复制后按 shotNo 排序，shotNo 为 null 的排最后；不修改原 list
        List<Shot> sorted = new ArrayList<>(shots);
        sorted.sort(Comparator.comparing(Shot::getShotNo, Comparator.nullsLast(Comparator.naturalOrder())));

        // 仅保留时长非空的镜头，时长必须为正数才参与统计
        List<Shot> valid = new ArrayList<>();
        for (Shot shot : sorted) {
            Integer d = shot.getDurationSeconds();
            if (d != null && d > 0) {
                valid.add(shot);
            }
        }

        if (valid.isEmpty()) {
            return new RhythmReport(new ArrayList<>(), 0, 0.0, 0.0);
        }

        int n = valid.size();
        double sum = 0.0;
        for (Shot shot : valid) {
            sum += shot.getDurationSeconds();
        }
        double mean = sum / n;

        double variance = 0.0;
        for (Shot shot : valid) {
            double diff = shot.getDurationSeconds() - mean;
            variance += diff * diff;
        }
        variance = variance / n;
        double std = Math.sqrt(variance);
        double cv = mean > 0 ? std / mean : 0.0;

        double totalSeconds = sum;
        double cutsPerMinute = totalSeconds > 0 ? (n * 60.0) / totalSeconds : 0.0;

        List<RhythmIssue> issues = new ArrayList<>();
        checkDurationOutlier(valid, mean, std, issues);
        checkTooUniform(valid, cv, cfg, issues);
        checkCutDensity(totalSeconds, cutsPerMinute, cfg, issues);
        checkMonotonousRun(valid, cfg, issues);
        checkOpeningAndEnding(valid, mean, issues);

        return new RhythmReport(issues, n, mean, cutsPerMinute);
    }

    /**
     * 规则 DURATION_OUTLIER：单镜时长落在均值 ±2 倍标准差之外 → WARN。
     *
     * @param shots  有效镜头列表
     * @param mean   均值
     * @param std    标准差
     * @param issues 问题收集器
     */
    private void checkDurationOutlier(List<Shot> shots, double mean, double std, List<RhythmIssue> issues) {
        if (std <= 0) {
            return;
        }
        double lower = mean - 2 * std;
        double upper = mean + 2 * std;
        for (Shot shot : shots) {
            double d = shot.getDurationSeconds();
            if (d < lower || d > upper) {
                issues.add(new RhythmIssue(
                        shotNoOf(shot),
                        shot.getId(),
                        "DURATION_OUTLIER",
                        ShotContinuityChecker.Severity.WARN,
                        String.format("镜头时长 %.2fs 偏离均值 %.2fs 超过 2 倍标准差（%.2fs）", d, mean, std),
                        "请确认该镜头时长为有意设计，否则调整至接近整体节奏"));
            }
        }
    }

    /**
     * 规则 RHYTHM_TOO_UNIFORM：变异系数低于阈值 → 1 条整体性 WARN。
     *
     * @param shots  有效镜头列表
     * @param cv     变异系数
     * @param config 配置
     * @param issues 问题收集器
     */
    private void checkTooUniform(List<Shot> shots, double cv, RhythmConfig config, List<RhythmIssue> issues) {
        if (cv < config.cvUniformThreshold()) {
            issues.add(new RhythmIssue(
                    0,
                    null,
                    "RHYTHM_TOO_UNIFORM",
                    ShotContinuityChecker.Severity.WARN,
                    String.format("镜头时长变异系数 %.3f 低于阈值 %.3f，节奏过于均匀", cv, config.cvUniformThreshold()),
                    "适当拉开长短镜头差异，制造节奏起伏"));
        }
    }

    /**
     * 规则 CUTS_TOO_SPARSE / CUTS_TOO_DENSE：按每分钟切镜数判断转场过稀或过密。
     *
     * @param totalSeconds   总时长（秒）
     * @param cutsPerMinute  每分钟切镜数
     * @param config         配置
     * @param issues         问题收集器
     */
    private void checkCutDensity(double totalSeconds, double cutsPerMinute, RhythmConfig config,
                                 List<RhythmIssue> issues) {
        if (totalSeconds > 60 && cutsPerMinute < config.sparseCutsPerMinute()) {
            issues.add(new RhythmIssue(
                    0,
                    null,
                    "CUTS_TOO_SPARSE",
                    ShotContinuityChecker.Severity.WARN,
                    String.format("每分钟切镜数 %.2f 低于阈值 %.2f，转场过稀", cutsPerMinute, config.sparseCutsPerMinute()),
                    "增加镜头数量或缩短单镜时长，提升信息密度"));
        }
        if (cutsPerMinute > config.denseCutsPerMinute()) {
            issues.add(new RhythmIssue(
                    0,
                    null,
                    "CUTS_TOO_DENSE",
                    ShotContinuityChecker.Severity.WARN,
                    String.format("每分钟切镜数 %.2f 高于阈值 %.2f，转场过密", cutsPerMinute, config.denseCutsPerMinute()),
                    "合并或延长部分镜头，避免观众视觉疲劳"));
        }
    }

    /**
     * 规则 MONOTONOUS_RUN：连续 N 个镜头两两时长差不超过 1s → 对段首记 1 条 WARN。
     *
     * @param shots  有效镜头列表
     * @param config 配置
     * @param issues 问题收集器
     */
    private void checkMonotonousRun(List<Shot> shots, RhythmConfig config, List<RhythmIssue> issues) {
        int runLength = (int) config.monotonousRunLength();
        if (runLength < 2 || shots.size() < runLength) {
            return;
        }
        int i = 0;
        while (i + runLength <= shots.size()) {
            boolean monotonous = true;
            for (int j = i; j < i + runLength - 1; j++) {
                double a = shots.get(j).getDurationSeconds();
                double b = shots.get(j + 1).getDurationSeconds();
                if (Math.abs(a - b) > 1.0) {
                    monotonous = false;
                    break;
                }
            }
            if (monotonous) {
                Shot first = shots.get(i);
                issues.add(new RhythmIssue(
                        shotNoOf(first),
                        first.getId(),
                        "MONOTONOUS_RUN",
                        ShotContinuityChecker.Severity.WARN,
                        String.format("自该镜起连续 %d 个镜头时长接近（两两差不超过 1s），节奏单调", runLength),
                        "在该段落中插入一个明显更长或更短的镜头打破单调"));
                i += runLength;
            } else {
                i++;
            }
        }
    }

    /**
     * 规则 SLOW_OPENING / DRAGGING_ENDING：开头拖沓与结尾拖沓。
     *
     * @param shots  有效镜头列表
     * @param mean   整体均值
     * @param issues 问题收集器
     */
    private void checkOpeningAndEnding(List<Shot> shots, double mean, List<RhythmIssue> issues) {
        if (shots.size() >= 3 && mean > 0) {
            double openingSum = 0.0;
            for (int i = 0; i < 3; i++) {
                openingSum += shots.get(i).getDurationSeconds();
            }
            double openingMean = openingSum / 3.0;
            if (openingMean > mean * 1.5) {
                issues.add(new RhythmIssue(
                        0,
                        null,
                        "SLOW_OPENING",
                        ShotContinuityChecker.Severity.INFO,
                        String.format("前 3 镜平均时长 %.2fs 超过整体均值 %.2fs 的 1.5 倍，开场偏慢", openingMean, mean),
                        "压缩开场镜头时长，尽快进入核心信息"));
            }
        }

        if (mean > 0) {
            Shot last = shots.get(shots.size() - 1);
            double lastDuration = last.getDurationSeconds();
            if (lastDuration > mean * 2) {
                issues.add(new RhythmIssue(
                        shotNoOf(last),
                        last.getId(),
                        "DRAGGING_ENDING",
                        ShotContinuityChecker.Severity.INFO,
                        String.format("末镜时长 %.2fs 超过整体均值 %.2fs 的 2 倍，收尾偏拖", lastDuration, mean),
                        "缩短末镜或在收尾前增加切镜"));
            }
        }
    }

    /**
     * 安全获取镜号，null 时回退为 0。
     *
     * @param shot 分镜
     * @return 镜号，null 时为 0
     */
    private int shotNoOf(Shot shot) {
        Integer shotNo = shot.getShotNo();
        return shotNo == null ? 0 : shotNo;
    }
}
