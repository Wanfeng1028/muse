package com.dramafactory.service.video;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/**
 * 视频通道多维评分卡（不可变值对象）。
 * 7 个维度取值均在 [0,1] 区间，构造时校验越界。
 * 加权总分权重：taskFit 0.30 / outputQuality 0.20 / control 0.15 /
 * reliability 0.15 / costEfficiency 0.10 / latency 0.05 / continuity 0.05。
 */
public final class ProviderScoreCard {

    public static final double W_TASK_FIT = 0.30;
    public static final double W_OUTPUT_QUALITY = 0.20;
    public static final double W_CONTROL = 0.15;
    public static final double W_RELIABILITY = 0.15;
    public static final double W_COST_EFFICIENCY = 0.10;
    public static final double W_LATENCY = 0.05;
    public static final double W_CONTINUITY = 0.05;

    private final double taskFit;
    private final double outputQuality;
    private final double control;
    private final double reliability;
    private final double costEfficiency;
    private final double latency;
    private final double continuity;

    public ProviderScoreCard(double taskFit, double outputQuality, double control, double reliability,
                             double costEfficiency, double latency, double continuity) {
        this.taskFit = check("taskFit", taskFit);
        this.outputQuality = check("outputQuality", outputQuality);
        this.control = check("control", control);
        this.reliability = check("reliability", reliability);
        this.costEfficiency = check("costEfficiency", costEfficiency);
        this.latency = check("latency", latency);
        this.continuity = check("continuity", continuity);
    }

    private static double check(String name, double value) {
        if (Double.isNaN(value) || value < 0.0 || value > 1.0) {
            throw new IllegalArgumentException("评分维度越界：" + name + "=" + value + "，要求取值 0-1");
        }
        return value;
    }

    public double taskFit() {
        return taskFit;
    }

    public double outputQuality() {
        return outputQuality;
    }

    public double control() {
        return control;
    }

    public double reliability() {
        return reliability;
    }

    public double costEfficiency() {
        return costEfficiency;
    }

    public double latency() {
        return latency;
    }

    public double continuity() {
        return continuity;
    }

    /** 按固定权重计算加权总分，结果落在 [0,1]。 */
    public double weightedScore() {
        return taskFit * W_TASK_FIT
                + outputQuality * W_OUTPUT_QUALITY
                + control * W_CONTROL
                + reliability * W_RELIABILITY
                + costEfficiency * W_COST_EFFICIENCY
                + latency * W_LATENCY
                + continuity * W_CONTINUITY;
    }

    /**
     * 生成人类可读的多行说明：逐维度原始分与加权贡献、加权总分、贡献最大的前 3 维度。
     */
    public String explain() {
        List<Contribution> contributions = new ArrayList<>();
        contributions.add(new Contribution("taskFit", taskFit, taskFit * W_TASK_FIT));
        contributions.add(new Contribution("outputQuality", outputQuality, outputQuality * W_OUTPUT_QUALITY));
        contributions.add(new Contribution("control", control, control * W_CONTROL));
        contributions.add(new Contribution("reliability", reliability, reliability * W_RELIABILITY));
        contributions.add(new Contribution("costEfficiency", costEfficiency, costEfficiency * W_COST_EFFICIENCY));
        contributions.add(new Contribution("latency", latency, latency * W_LATENCY));
        contributions.add(new Contribution("continuity", continuity, continuity * W_CONTINUITY));

        List<Contribution> top = new ArrayList<>(contributions);
        top.sort(Comparator.comparingDouble(Contribution::weighted).reversed());

        StringBuilder sb = new StringBuilder();
        sb.append("通道评分卡：").append('\n');
        sb.append(String.format(Locale.ROOT, "  加权总分 = %.4f%n", weightedScore()));
        sb.append("  维度明细（原始分/权重/加权贡献）：").append('\n');
        for (Contribution c : contributions) {
            sb.append(String.format(Locale.ROOT, "    %-16s %.2f × %.2f = %.4f%n",
                    c.name(), c.raw(), weightOf(c.name()), c.weighted()));
        }
        sb.append("  贡献最大的前 3 维度：").append('\n');
        int limit = Math.min(3, top.size());
        for (int i = 0; i < limit; i++) {
            Contribution c = top.get(i);
            sb.append(String.format(Locale.ROOT, "    %d) %-16s 贡献 %.4f（原始分 %.2f）%n",
                    i + 1, c.name(), c.weighted(), c.raw()));
        }
        return sb.toString();
    }

    private static double weightOf(String name) {
        switch (name) {
            case "taskFit":
                return W_TASK_FIT;
            case "outputQuality":
                return W_OUTPUT_QUALITY;
            case "control":
                return W_CONTROL;
            case "reliability":
                return W_RELIABILITY;
            case "costEfficiency":
                return W_COST_EFFICIENCY;
            case "latency":
                return W_LATENCY;
            case "continuity":
                return W_CONTINUITY;
            default:
                return 0.0;
        }
    }

    private record Contribution(String name, double raw, double weighted) {
    }

    @Override
    public String toString() {
        return "ProviderScoreCard{" +
                "taskFit=" + taskFit +
                ", outputQuality=" + outputQuality +
                ", control=" + control +
                ", reliability=" + reliability +
                ", costEfficiency=" + costEfficiency +
                ", latency=" + latency +
                ", continuity=" + continuity +
                ", weightedScore=" + weightedScore() +
                '}';
    }
}
