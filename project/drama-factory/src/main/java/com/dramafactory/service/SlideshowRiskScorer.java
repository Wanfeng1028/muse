package com.dramafactory.service;

import com.dramafactory.model.Shot;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 幻灯片风险评分器。
 * <p>
 * 对视频方案在 6 个维度上进行评分，这些维度可可靠预测输出是否更像幻灯片而非导演视频。
 * 每个维度评分 0-5（越低越好）。
 * </p>
 */
@Service
public class SlideshowRiskScorer {

    /**
     * 场景特征记录，用于评分计算。
     *
     * @param type             场景类型
     * @param description      场景描述
     * @param shotSize         景别
     * @param cameraMovement   运镜方式
     * @param hasIntent        是否陈述拍摄意图
     * @param heroMoment       是否高光时刻
     * @param lightingDefined 是否定义灯光
     */
    public record SceneFeatures(String type, String description, String shotSize, String cameraMovement, boolean hasIntent, boolean heroMoment, boolean lightingDefined) {
    }

    /**
     * 维度评分结果。
     *
     * @param score  得分
     * @param reason 得分原因
     */
    public record DimensionScore(double score, String reason) {
    }

    /**
     * 幻灯片风险报告。
     *
     * @param average       六维平均分
     * @param verdict       判定结果（strong/acceptable/revise/fail）
     * @param verdictLabel  判定中文标签
     * @param scenesChecked 检查的场景数
     * @param dimensions    各维度评分
     * @param renderRuntime 渲染运行时
     */
    public record SlideshowRiskReport(double average, String verdict, String verdictLabel, int scenesChecked, Map<String, DimensionScore> dimensions, String renderRuntime) {
    }

    /**
     * 对场景列表进行幻灯片风险评分。
     *
     * @param scenes         场景特征列表
     * @param rendererFamily 渲染器家族
     * @param renderRuntime  渲染运行时
     * @return 评分报告
     */
    public SlideshowRiskReport score(List<SceneFeatures> scenes, String rendererFamily, String renderRuntime) {
        if (scenes == null || scenes.isEmpty()) {
            return new SlideshowRiskReport(5.0, "fail", "不通过", 0, new LinkedHashMap<>(), renderRuntime);
        }

        Map<String, DimensionScore> dimensions = new LinkedHashMap<>();
        dimensions.put("repetition", scoreRepetition(scenes));
        dimensions.put("decorative_visuals", scoreDecorative(scenes));
        dimensions.put("weak_motion", scoreWeakMotion(scenes));
        dimensions.put("weak_shot_intent", scoreWeakIntent(scenes));
        dimensions.put("typography_overreliance", scoreTypography(scenes));
        dimensions.put("unsupported_cinematic_claims", scoreCinematicClaims(scenes, rendererFamily));

        double average = dimensions.values().stream()
                .mapToDouble(DimensionScore::score)
                .average()
                .orElse(0.0);
        average = round2(average);

        String verdict;
        String verdictLabel;
        if (average < 2.0) {
            verdict = "strong";
            verdictLabel = "强";
        } else if (average < 3.0) {
            verdict = "acceptable";
            verdictLabel = "可接受";
        } else if (average < 4.0) {
            verdict = "revise";
            verdictLabel = "需修改";
        } else {
            verdict = "fail";
            verdictLabel = "不通过";
        }

        return new SlideshowRiskReport(average, verdict, verdictLabel, scenes.size(), dimensions, renderRuntime);
    }

    /**
     * 对镜头列表进行幻灯片风险评分，按 shotNo 排序后转换。
     *
     * @param shots          镜头列表
     * @param rendererFamily 渲染器家族
     * @return 评分报告
     */
    public SlideshowRiskReport scoreShots(List<Shot> shots, String rendererFamily) {
        if (shots == null || shots.isEmpty()) {
            return new SlideshowRiskReport(5.0, "fail", "不通过", 0, new LinkedHashMap<>(), null);
        }
        List<Shot> sorted = new ArrayList<>(shots);
        sorted.sort(Comparator.comparing(Shot::getShotNo));
        List<SceneFeatures> features = sorted.stream()
                .map(SlideshowRiskScorer::fromShot)
                .collect(Collectors.toList());
        return score(features, rendererFamily, null);
    }

    /**
     * 将 Shot 映射为 SceneFeatures。
     * <p>
     * type：description 含「文字卡」「标题卡」「字幕卡」或 "text_card" → "text_card"；
     * 否则 dialogue 非空 → "dialogue"；否则 "visual"。
     * description null→""。shotSize 枚举 name()，null→"none"。
     * cameraMovement：GU_DING→"static"，null→"unspecified"，其余枚举 name()。
     * hasIntent：videoPrompt 非 null 且 trim 非空。
     * heroMoment：description 或 videoPrompt 含「高潮」「高光」或小写含 "hero"。
     * lightingDefined：videoPrompt 含「灯光」「光影」「光线」「打光」或小写含 "lighting"。
     * </p>
     *
     * @param shot 镜头对象
     * @return 场景特征
     */
    public static SceneFeatures fromShot(Shot shot) {
        String description = shot.getDescription() == null ? "" : shot.getDescription();

        String type;
        if (description.contains("文字卡") || description.contains("标题卡") || description.contains("字幕卡") || description.contains("text_card")) {
            type = "text_card";
        } else if (shot.getDialogue() != null && !shot.getDialogue().trim().isEmpty()) {
            type = "dialogue";
        } else {
            type = "visual";
        }

        String shotSize = shot.getShotSize() == null ? "none" : shot.getShotSize().name();

        String cameraMovement;
        if (shot.getCameraMove() == null) {
            cameraMovement = "unspecified";
        } else if ("GU_DING".equals(shot.getCameraMove().name())) {
            cameraMovement = "static";
        } else {
            cameraMovement = shot.getCameraMove().name();
        }

        boolean hasIntent = shot.getVideoPrompt() != null && !shot.getVideoPrompt().trim().isEmpty();

        boolean heroMoment = false;
        if (description.contains("高潮") || description.contains("高光") || description.toLowerCase().contains("hero")) {
            heroMoment = true;
        } else if (shot.getVideoPrompt() != null) {
            String vp = shot.getVideoPrompt();
            if (vp.contains("高潮") || vp.contains("高光") || vp.toLowerCase().contains("hero")) {
                heroMoment = true;
            }
        }

        boolean lightingDefined = false;
        if (shot.getVideoPrompt() != null) {
            String vp = shot.getVideoPrompt();
            if (vp.contains("灯光") || vp.contains("光影") || vp.contains("光线") || vp.contains("打光") || vp.toLowerCase().contains("lighting")) {
                lightingDefined = true;
            }
        }

        return new SceneFeatures(type, description, shotSize, cameraMovement, hasIntent, heroMoment, lightingDefined);
    }

    /**
     * 评分：视觉重复度。
     * <p>
     * scenes&lt;3 → 0.0。否则 type 众数占比&gt;0.7 → +2.0；
     * description 小写取前 50 字符去重比&lt;0.6 → +1.5；
     * shotSize 众数占比&gt;0.6 → +1.5；封顶 5.0。
     * </p>
     */
    private DimensionScore scoreRepetition(List<SceneFeatures> scenes) {
        if (scenes.size() < 3) {
            return new DimensionScore(0.0, "场景太少，无法评估重复度");
        }

        Map<String, Long> typeCounts = scenes.stream()
                .collect(Collectors.groupingBy(SceneFeatures::type, LinkedHashMap::new, Collectors.counting()));
        long maxTypeCount = typeCounts.values().stream().mapToLong(Long::longValue).max().orElse(0);
        String mostCommonType = typeCounts.entrySet().stream()
                .max(Map.Entry.comparingByValue())
                .map(Map.Entry::getKey)
                .orElse("unknown");
        double typeRatio = (double) maxTypeCount / scenes.size();

        Set<String> uniqueDescriptions = scenes.stream()
                .map(s -> {
                    String d = s.description().toLowerCase();
                    return d.substring(0, Math.min(50, d.length()));
                })
                .collect(Collectors.toSet());
        double uniqueDescRatio = (double) uniqueDescriptions.size() / scenes.size();

        Map<String, Long> sizeCounts = scenes.stream()
                .collect(Collectors.groupingBy(SceneFeatures::shotSize, LinkedHashMap::new, Collectors.counting()));
        long maxSizeCount = sizeCounts.values().stream().mapToLong(Long::longValue).max().orElse(0);
        double sizeRatio = (double) maxSizeCount / scenes.size();

        double score = 0.0;
        List<String> reasons = new ArrayList<>();

        if (typeRatio > 0.7) {
            score += 2.0;
            reasons.add(String.format("场景类型 '%s' 占比达 %d%%", mostCommonType, Math.round(typeRatio * 100)));
        }
        if (uniqueDescRatio < 0.6) {
            score += 1.5;
            reasons.add(String.format("仅 %d%% 的描述唯一", Math.round(uniqueDescRatio * 100)));
        }
        if (sizeRatio > 0.6) {
            score += 1.5;
            reasons.add(String.format("%d%% 的场景使用相同景别", Math.round(sizeRatio * 100)));
        }

        score = Math.min(5.0, score);
        String reason = reasons.isEmpty() ? "多样性良好" : String.join("; ", reasons);
        return new DimensionScore(score, reason);
    }

    /**
     * 评分：装饰性视觉。
     * <p>
     * 剧坊 Shot 无独立 role 字段，以 hasIntent 为"是否陈述目的"唯一判据。
     * hasIntent=false 占比 ratio → min(5, ratio*5) round 1 位。
     * </p>
     */
    private DimensionScore scoreDecorative(List<SceneFeatures> scenes) {
        int decorativeCount = 0;
        for (SceneFeatures s : scenes) {
            if (!s.hasIntent()) {
                decorativeCount++;
            }
        }
        double ratio = (double) decorativeCount / scenes.size();
        double score = Math.min(5.0, ratio * 5.0);
        score = round1(score);

        String reason;
        if (ratio > 0.5) {
            reason = String.format("%d/%d 个场景未陈述目的（无 information_role、narrative_role 或 shot_intent）", decorativeCount, scenes.size());
        } else if (ratio > 0.2) {
            reason = String.format("%d/%d 个场景缺乏陈述目的", decorativeCount, scenes.size());
        } else {
            reason = "大多数场景有明确的表达目的";
        }

        return new DimensionScore(score, reason);
    }

    /**
     * 评分：运镜薄弱。
     * <p>
     * cameraMovement 不属于 {"static","unspecified",null} 为运动镜头；
     * 无运动镜头 → 1.5；否则无意图运动占比 ratio → min(5, ratio*4) round 1 位。
     * </p>
     */
    private DimensionScore scoreWeakMotion(List<SceneFeatures> scenes) {
        int totalMoving = 0;
        int purposelessMoving = 0;

        for (SceneFeatures s : scenes) {
            String movement = s.cameraMovement();
            if (!"static".equals(movement) && !"unspecified".equals(movement) && movement != null) {
                totalMoving++;
                if (!s.hasIntent()) {
                    purposelessMoving++;
                }
            }
        }

        if (totalMoving == 0) {
            return new DimensionScore(1.5, "未定义运镜（静态风格可接受）");
        }

        double ratio = (double) purposelessMoving / totalMoving;
        double score = Math.min(5.0, ratio * 4.0);
        score = round1(score);

        String reason;
        if (ratio > 0.5) {
            reason = String.format("%d/%d 个运动镜头缺乏 shot_intent", purposelessMoving, totalMoving);
        } else {
            reason = "运镜看起来有目的性";
        }

        return new DimensionScore(score, reason);
    }

    /**
     * 评分：镜头意图薄弱。
     * <p>
     * hasIntent 占比 ratio → min(5,(1-ratio)*5) round 1 位。
     * </p>
     */
    private DimensionScore scoreWeakIntent(List<SceneFeatures> scenes) {
        int withIntent = 0;
        for (SceneFeatures s : scenes) {
            if (s.hasIntent()) {
                withIntent++;
            }
        }
        double ratio = (double) withIntent / scenes.size();
        double score = Math.min(5.0, (1.0 - ratio) * 5.0);
        score = round1(score);

        String reason;
        if (ratio < 0.3) {
            reason = String.format("仅 %d/%d 个场景有 shot_intent — 大多数镜头缺乏目的", withIntent, scenes.size());
        } else if (ratio < 0.6) {
            reason = String.format("%d/%d 个场景有 shot_intent", withIntent, scenes.size());
        } else {
            reason = "镜头意图覆盖良好";
        }

        return new DimensionScore(score, reason);
    }

    /**
     * 评分：文字优先过度依赖。
     * <p>
     * type ∈ {"text_card","stat_card","kpi_grid"} 占比：
     * &gt;0.6→4.0；&gt;0.4→2.5；&gt;0.2→1.0；否则 0.0。
     * </p>
     */
    private DimensionScore scoreTypography(List<SceneFeatures> scenes) {
        int textScenes = 0;
        for (SceneFeatures s : scenes) {
            String type = s.type();
            if ("text_card".equals(type) || "stat_card".equals(type) || "kpi_grid".equals(type)) {
                textScenes++;
            }
        }
        double ratio = (double) textScenes / scenes.size();

        double score;
        String reason;
        if (ratio > 0.6) {
            score = 4.0;
            reason = String.format("%d/%d 个场景是文字/数据卡片 — 视频感觉像动态幻灯片", textScenes, scenes.size());
        } else if (ratio > 0.4) {
            score = 2.5;
            reason = String.format("%d/%d 个场景是文字类 — 考虑与视觉场景平衡", textScenes, scenes.size());
        } else if (ratio > 0.2) {
            score = 1.0;
            reason = "文字与视觉内容平衡";
        } else {
            score = 0.0;
            reason = "视觉优先方法";
        }

        return new DimensionScore(score, reason);
    }

    /**
     * 评分：电影感声明缺乏结构支撑。
     * <p>
     * rendererFamily 为 null 或不含 "cinematic"（忽略大小写）→ 0.0。
     * 否则：heroMoment 数=0 记 1 issue；运动镜头数 &lt; scenes*0.3 记 1 issue；
     * lightingDefined 数 &lt; scenes*0.3 记 1 issue；得分 min(5, issues*1.8) round 1 位。
     * </p>
     */
    private DimensionScore scoreCinematicClaims(List<SceneFeatures> scenes, String rendererFamily) {
        boolean isCinematic = rendererFamily != null && rendererFamily.toLowerCase().contains("cinematic");

        if (!isCinematic) {
            return new DimensionScore(0.0, "未声明电影感处理");
        }

        List<String> issues = new ArrayList<>();

        int heroCount = 0;
        for (SceneFeatures s : scenes) {
            if (s.heroMoment()) {
                heroCount++;
            }
        }
        if (heroCount == 0) {
            issues.add("声明电影感但未定义 hero_moment");
        }

        int hasMovement = 0;
        for (SceneFeatures s : scenes) {
            if (!"static".equals(s.cameraMovement())) {
                hasMovement++;
            }
        }
        if (hasMovement < scenes.size() * 0.3) {
            issues.add(String.format("声明电影感但仅 %d/%d 个场景有运镜", hasMovement, scenes.size()));
        }

        int hasLighting = 0;
        for (SceneFeatures s : scenes) {
            if (s.lightingDefined()) {
                hasLighting++;
            }
        }
        if (hasLighting < scenes.size() * 0.3) {
            issues.add(String.format("声明电影感但仅 %d/%d 个场景定义了灯光", hasLighting, scenes.size()));
        }

        double score = Math.min(5.0, issues.size() * 1.8);
        score = round1(score);
        String reason = issues.isEmpty() ? "电影感声明有结构支撑" : String.join("; ", issues);

        return new DimensionScore(score, reason);
    }

    private double round1(double v) {
        return Math.round(v * 10) / 10.0;
    }

    private double round2(double v) {
        return Math.round(v * 100) / 100.0;
    }
}
