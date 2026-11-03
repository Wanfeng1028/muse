package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ProviderScoringService 七个维度边界、排序稳定性、VideoProviderRouter 降级与决策记录的深挖测试。
 * 期望值全部按事实来源里的实现手算，不拍脑袋。
 */
class ProviderRoutingScoringDeepTest {

    private static final double EPS = 1e-9;

    private ProviderScoringService newScoring() {
        return new ProviderScoringService();
    }

    /** 构造一个默认候选：bestFor 空、cost 0.05、quality 0.5、reliability 0.5、control 空、MEDIUM、不生产稳定。 */
    private ProviderScoringService.ProviderCandidate candidate(String name) {
        return new ProviderScoringService.ProviderCandidate(
                name, Set.of(), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
    }

    /** 只给一个候选打分，取返回列表的第一个。 */
    private ProviderScoringService.ScoredProvider scoreOne(ProviderScoringService.ProviderCandidate c,
                                                           ProviderScoringService.TaskContext ctx) {
        List<ProviderScoringService.ScoredProvider> ranked = newScoring().rank(List.of(c), ctx);
        assertEquals(1, ranked.size());
        return ranked.get(0);
    }

    /** 空上下文：intent 空、无风格词、无预算、quality 0、无锁定、无动态要求、assetType 空。 */
    private ProviderScoringService.TaskContext emptyContext() {
        return new ProviderScoringService.TaskContext("", Set.of(), null, null, 0.0, Set.of(), false, null);
    }

    // ---------- A1 taskFit 缺失数据 ----------

    @Test
    void taskFitEmptyBestForFallsBackToDefault() {
        // bestFor 空集合 → 直接返回 DEFAULT_TASK_FIT = 0.3。
        ProviderScoringService.ScoredProvider scored = scoreOne(candidate("p1"), emptyContext());
        assertEquals(0.3, scored.dimensions().get("taskFit"), EPS);
    }

    // ---------- A2 taskFit 零分 ----------

    @Test
    void taskFitNoOverlapGivesZeroAndLowFitReason() {
        // intent 切词 {cinematic,motion,clip}，bestFor {painting}，交集 0 → 0/min(3,1)=0.0；
        // cost 0.05 且无预算字段 → 走 remaining==null 分支，0.05<0.2 → 0.7，不产生"超出预算上限"。
        // taskFit 0.0 < 0.3 → 追加"任务匹配度低"。
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p1", Set.of("painting"), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.TaskContext ctx = new ProviderScoringService.TaskContext(
                "cinematic motion clip", Set.of(), null, null, 0.0, Set.of(), false, null);

        ProviderScoringService.ScoredProvider scored = scoreOne(c, ctx);
        assertEquals(0.0, scored.dimensions().get("taskFit"), EPS);
        assertTrue(scored.reasons().contains("任务匹配度低"));
    }

    // ---------- A3 taskFit 满分 ----------

    @Test
    void taskFitFullOverlapGivesOne() {
        // intent 切词 {cinematic,motion,clip}，bestFor {cinematic,motion,clip}，交集 3，
        // min(3,3)=3 → 3/3=1.0。
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p1", Set.of("cinematic", "motion", "clip"), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.TaskContext ctx = new ProviderScoringService.TaskContext(
                "cinematic motion clip", Set.of(), null, null, 0.0, Set.of(), false, null);

        ProviderScoringService.ScoredProvider scored = scoreOne(c, ctx);
        assertEquals(1.0, scored.dimensions().get("taskFit"), EPS);
    }

    // ---------- A4 动态镜头惩罚 ----------

    @Test
    void taskFitMotionPenaltyWhenBestForHasNoMotionToken() {
        // 甲 bestFor {cinematic,painting}：intent 切词 {cinematic,motion,clip}，交集 {cinematic}=1，
        // min(3,2)=2 → 0.5；motionRequired=true 且 assetType="video"，bestFor 切词无 video/motion/clip/tvc/film
        // → 0.5*0.2 = 0.1。
        // 乙 bestFor {cinematic,motion}：交集 {cinematic,motion}=2，min(3,2)=2 → 1.0；含 motion 不惩罚 → 1.0。
        ProviderScoringService.ProviderCandidate jia = new ProviderScoringService.ProviderCandidate(
                "jia", Set.of("cinematic", "painting"), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.ProviderCandidate yi = new ProviderScoringService.ProviderCandidate(
                "yi", Set.of("cinematic", "motion"), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.TaskContext ctx = new ProviderScoringService.TaskContext(
                "cinematic motion clip", Set.of(), null, null, 0.0, Set.of(), true, "video");

        List<ProviderScoringService.ScoredProvider> ranked =
                newScoring().rank(List.of(jia, yi), ctx);
        Map<String, Double> byName = new LinkedHashMap<>();
        for (ProviderScoringService.ScoredProvider sp : ranked) {
            byName.put(sp.providerName(), sp.dimensions().get("taskFit"));
        }
        assertEquals(0.1, byName.get("jia"), EPS);
        assertEquals(1.0, byName.get("yi"), EPS);
    }

    // ---------- A5 quality 边界 ----------

    @Test
    void qualityBoundariesWithAndWithoutProductionStability() {
        // 稳定 + 0.97 → min(1.0, 1.02) = 1.0。
        ProviderScoringService.ProviderCandidate stableHigh = new ProviderScoringService.ProviderCandidate(
                "a", Set.of(), 0.05, 0.97, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, true);
        assertEquals(1.0, scoreOne(stableHigh, emptyContext()).dimensions().get("quality"), EPS);

        // 稳定 + 0.8 → 0.85。
        ProviderScoringService.ProviderCandidate stableMid = new ProviderScoringService.ProviderCandidate(
                "b", Set.of(), 0.05, 0.8, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, true);
        assertEquals(0.85, scoreOne(stableMid, emptyContext()).dimensions().get("quality"), EPS);

        // 不稳定 + 0.8 → 0.8。
        ProviderScoringService.ProviderCandidate unstable = new ProviderScoringService.ProviderCandidate(
                "c", Set.of(), 0.05, 0.8, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        assertEquals(0.8, scoreOne(unstable, emptyContext()).dimensions().get("quality"), EPS);
    }

    // ---------- A6 control 边界 ----------

    @Test
    void controlEmptyFeaturesGivesDefault() {
        // controlFeatures 空 → DEFAULT_CONTROL = 0.3。
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p", Set.of(), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        assertEquals(0.3, scoreOne(c, emptyContext()).dimensions().get("control"), EPS);
    }

    @Test
    void controlOnlyReferenceImage() {
        // 权重总和 2.0+1.5+1.5+1.3+1.0+0.7+0.5 = 8.5，分母 8.5*0.5 = 4.25；
        // 只命中 referenceImage 权重 2.0 → 2.0/4.25 = 0.470588...。
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p", Set.of(), 0.05, 0.5, 0.5, Set.of("referenceImage"),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        assertEquals(0.4706, scoreOne(c, emptyContext()).dimensions().get("control"), 1e-4);
    }

    @Test
    void controlAllFeaturesClampedToOne() {
        // 全命中 8.5/4.25 = 2.0 → min(1.0, 2.0) = 1.0。
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p", Set.of(), 0.05, 0.5, 0.5,
                Set.of("referenceImage", "cameraControl", "styleTransfer", "img2img",
                        "negativePrompt", "aspectRatio", "seed"),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        assertEquals(1.0, scoreOne(c, emptyContext()).dimensions().get("control"), EPS);
    }

    // ---------- A7 costEfficiency 边界 ----------

    @Test
    void costZeroGivesOne() {
        // cost <= 0 → 1.0。
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p", Set.of(), 0.0, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        assertEquals(1.0, scoreOne(c, emptyContext()).dimensions().get("costEfficiency"), EPS);
    }

    @Test
    void costOverBudgetCapGivesZeroAndReason() {
        // cost 12 > cap 5 → 0.0；costEfficiency==0 → 追加"超出预算上限"。
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p", Set.of(), 12.0, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.TaskContext ctx = new ProviderScoringService.TaskContext(
                "", Set.of(), 5.0, null, 0.0, Set.of(), false, null);
        ProviderScoringService.ScoredProvider scored = scoreOne(c, ctx);
        assertEquals(0.0, scored.dimensions().get("costEfficiency"), EPS);
        assertTrue(scored.reasons().contains("超出预算上限"));
    }

    @Test
    void costRemainingZeroGivesZero() {
        // remaining 0.0 <= 0.0 → 0.0；costEfficiency==0 → 追加"超出预算上限"。
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p", Set.of(), 1.0, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.TaskContext ctx = new ProviderScoringService.TaskContext(
                "", Set.of(), null, 0.0, 0.0, Set.of(), false, null);
        ProviderScoringService.ScoredProvider scored = scoreOne(c, ctx);
        assertEquals(0.0, scored.dimensions().get("costEfficiency"), EPS);
        assertTrue(scored.reasons().contains("超出预算上限"));
    }

    @Test
    void costToRemainingRatioBranches() {
        // 3.0/5.0 = 0.6 > 0.5 → 0.1。
        assertEquals(0.1, costWithRemaining(3.0, 5.0), EPS);
        // 2.0/5.0 = 0.4，>0.2 且 <=0.5 → 0.5。
        assertEquals(0.5, costWithRemaining(2.0, 5.0), EPS);
        // 1.0/5.0 = 0.2，不 >0.2 → 0.8。
        assertEquals(0.8, costWithRemaining(1.0, 5.0), EPS);
    }

    private double costWithRemaining(double cost, double remaining) {
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p", Set.of(), cost, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.TaskContext ctx = new ProviderScoringService.TaskContext(
                "", Set.of(), null, remaining, 0.0, Set.of(), false, null);
        return scoreOne(c, ctx).dimensions().get("costEfficiency");
    }

    @Test
    void costNoBudgetBranches() {
        // remaining == null 分支：0.03<0.05 → 0.9；0.15<0.2 → 0.7；0.5<1.0 → 0.5；5.0 → 0.3。
        assertEquals(0.9, costNoBudget(0.03), EPS);
        assertEquals(0.7, costNoBudget(0.15), EPS);
        assertEquals(0.5, costNoBudget(0.5), EPS);
        assertEquals(0.3, costNoBudget(5.0), EPS);
    }

    private double costNoBudget(double cost) {
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "p", Set.of(), cost, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        return scoreOne(c, emptyContext()).dimensions().get("costEfficiency");
    }

    // ---------- A8 latency 三档 ----------

    @Test
    void latencyThreeClasses() {
        // FAST 1.0 / MEDIUM 0.6 / SLOW 0.3。
        ProviderScoringService.ProviderCandidate fast = new ProviderScoringService.ProviderCandidate(
                "f", Set.of(), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.FAST, false);
        ProviderScoringService.ProviderCandidate medium = new ProviderScoringService.ProviderCandidate(
                "m", Set.of(), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.ProviderCandidate slow = new ProviderScoringService.ProviderCandidate(
                "s", Set.of(), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.SLOW, false);

        assertEquals(1.0, scoreOne(fast, emptyContext()).dimensions().get("latency"), EPS);
        assertEquals(0.6, scoreOne(medium, emptyContext()).dimensions().get("latency"), EPS);
        assertEquals(0.3, scoreOne(slow, emptyContext()).dimensions().get("latency"), EPS);
    }

    // ---------- A9 continuity 三档 ----------

    @Test
    void continuityThreeBranches() {
        // locked 空 → 0.5。
        assertEquals(0.5, continuityWith(Set.of(), "p1"), EPS);
        // locked 含候选名 → 0.9。
        assertEquals(0.9, continuityWith(Set.of("p1"), "p1"), EPS);
        // locked 非空但不含候选名 → 0.4。
        assertEquals(0.4, continuityWith(Set.of("other"), "p1"), EPS);
    }

    private double continuityWith(Set<String> locked, String name) {
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                name, Set.of(), 0.05, 0.5, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.TaskContext ctx = new ProviderScoringService.TaskContext(
                "", Set.of(), null, null, 0.0, locked, false, null);
        return scoreOne(c, ctx).dimensions().get("continuity");
    }

    // ---------- A10 ScoreCard 权重逐个验证 ----------

    @Test
    void scoreCardEachWeight() {
        // 每个维度单点 1，其它 0，得到的加权分就是该维度的权重。
        assertEquals(0.30, new ProviderScoreCard(1, 0, 0, 0, 0, 0, 0).weightedScore(), 1e-9);
        assertEquals(0.20, new ProviderScoreCard(0, 1, 0, 0, 0, 0, 0).weightedScore(), 1e-9);
        assertEquals(0.15, new ProviderScoreCard(0, 0, 1, 0, 0, 0, 0).weightedScore(), 1e-9);
        assertEquals(0.15, new ProviderScoreCard(0, 0, 0, 1, 0, 0, 0).weightedScore(), 1e-9);
        assertEquals(0.10, new ProviderScoreCard(0, 0, 0, 0, 1, 0, 0).weightedScore(), 1e-9);
        assertEquals(0.05, new ProviderScoreCard(0, 0, 0, 0, 0, 1, 0).weightedScore(), 1e-9);
        assertEquals(0.05, new ProviderScoreCard(0, 0, 0, 0, 0, 0, 1).weightedScore(), 1e-9);
    }

    @Test
    void scoreCardAllOnesAndAllZeros() {
        // 权重和 = 0.30+0.20+0.15+0.15+0.10+0.05+0.05 = 1.0。
        assertEquals(1.0, new ProviderScoreCard(1, 1, 1, 1, 1, 1, 1).weightedScore(), 1e-9);
        assertEquals(0.0, new ProviderScoreCard(0, 0, 0, 0, 0, 0, 0).weightedScore(), 1e-9);
    }

    @Test
    void scoreCardRejectsOutOfRangeAndNaN() {
        // -0.1 越界 → IllegalArgumentException。
        assertThrows(IllegalArgumentException.class,
                () -> new ProviderScoreCard(-0.1, 0, 0, 0, 0, 0, 0));
        // NaN → IllegalArgumentException。
        assertThrows(IllegalArgumentException.class,
                () -> new ProviderScoreCard(Double.NaN, 0, 0, 0, 0, 0, 0));
    }

    // ---------- B1 空输入 ----------

    @Test
    void rankEmptyOrNullInputReturnsEmpty() {
        ProviderScoringService svc = newScoring();
        assertTrue(svc.rank(List.of(), emptyContext()).isEmpty());
        assertTrue(svc.rank(null, emptyContext()).isEmpty());
    }

    // ---------- B2 平局保序 ----------

    @Test
    void rankTieKeepsInputOrder() {
        // 两个候选除名字外全部一样，加权分相同；List.sort 稳定 → 保持输入顺序。
        ProviderScoringService.ProviderCandidate first = new ProviderScoringService.ProviderCandidate(
                "first", Set.of(), 0.05, 0.8, 0.8, Set.of(),
                ProviderScoringService.LatencyClass.FAST, false);
        ProviderScoringService.ProviderCandidate second = new ProviderScoringService.ProviderCandidate(
                "second", Set.of(), 0.05, 0.8, 0.8, Set.of(),
                ProviderScoringService.LatencyClass.FAST, false);

        List<ProviderScoringService.ScoredProvider> ranked =
                newScoring().rank(List.of(first, second), emptyContext());
        assertEquals(2, ranked.size());
        assertEquals("first", ranked.get(0).providerName());
        assertEquals("second", ranked.get(1).providerName());
        assertEquals(ranked.get(0).weightedScore(), ranked.get(1).weightedScore(), EPS);
    }

    // ---------- B3 多次调用一致 ----------

    @Test
    void rankRepeatedCallsIdentical() {
        // 同一输入连续调三次，名字序列和加权分完全一样。
        ProviderScoringService.ProviderCandidate a = new ProviderScoringService.ProviderCandidate(
                "a", Set.of("cinematic"), 0.05, 0.9, 0.9, Set.of("referenceImage"),
                ProviderScoringService.LatencyClass.FAST, true);
        ProviderScoringService.ProviderCandidate b = new ProviderScoringService.ProviderCandidate(
                "b", Set.of("motion"), 0.5, 0.6, 0.7, Set.of("seed"),
                ProviderScoringService.LatencyClass.MEDIUM, false);
        ProviderScoringService.ProviderCandidate c = new ProviderScoringService.ProviderCandidate(
                "c", Set.of(), 2.0, 0.4, 0.5, Set.of(),
                ProviderScoringService.LatencyClass.SLOW, false);
        ProviderScoringService.TaskContext ctx = new ProviderScoringService.TaskContext(
                "cinematic motion", Set.of(), null, null, 0.0, Set.of(), false, null);

        ProviderScoringService svc = newScoring();
        List<ProviderScoringService.ScoredProvider> r1 = svc.rank(List.of(a, b, c), ctx);
        List<ProviderScoringService.ScoredProvider> r2 = svc.rank(List.of(a, b, c), ctx);
        List<ProviderScoringService.ScoredProvider> r3 = svc.rank(List.of(a, b, c), ctx);

        assertEquals(r1.size(), r2.size());
        assertEquals(r1.size(), r3.size());
        for (int i = 0; i < r1.size(); i++) {
            assertEquals(r1.get(i).providerName(), r2.get(i).providerName());
            assertEquals(r1.get(i).providerName(), r3.get(i).providerName());
            assertEquals(r1.get(i).weightedScore(), r2.get(i).weightedScore(), EPS);
            assertEquals(r1.get(i).weightedScore(), r3.get(i).weightedScore(), EPS);
        }
    }

    // ---------- B4 rankedChain 平局 ----------

    @Test
    void rankedChainTieKeepsChainOrder() {
        // agnes 与 minimax 评分卡完全相同（七维全 0.5）→ 加权分相等 → 保持 chain 原顺序，agnes 在前。
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProviderRouter router = new VideoProviderRouter(null, env, null);

        ProviderScoreCard card = new ProviderScoreCard(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5);
        Map<String, ProviderScoreCard> scores = new LinkedHashMap<>();
        scores.put("agnes", card);
        scores.put("minimax", card);

        List<String> ranked = router.rankedChain(null, scores);
        assertEquals("agnes", ranked.get(0));
        assertEquals("minimax", ranked.get(1));
    }

    // ---------- B5 未打分通道兜底 ----------

    @Test
    void rankedChainUnscoredKeepsChainOrder() {
        // 只给 agnes 打分，其余未打分按 chain 原顺序排后面。
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProviderRouter router = new VideoProviderRouter(null, env, null);

        Map<String, ProviderScoreCard> scores = new LinkedHashMap<>();
        scores.put("agnes", new ProviderScoreCard(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5));

        List<String> ranked = router.rankedChain(null, scores);
        assertEquals(List.of("agnes", "minimax", "novai", "doubao", "hyperframes", "htmlrender", "painted"), ranked);

        // 空 map 时与 chain(null) 完全一致。
        List<String> withEmpty = router.rankedChain(null, Map.of());
        assertEquals(router.chain(null), withEmpty);
    }

    // ---------- C1 全部抛异常 ----------

    @Test
    void submitAllProvidersThrowRuntimeException() {
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        VideoProvider agnes = Mockito.mock(VideoProvider.class);
        VideoProvider minimax = Mockito.mock(VideoProvider.class);
        VideoProvider novai = Mockito.mock(VideoProvider.class);
        VideoProvider doubao = Mockito.mock(VideoProvider.class);
        VideoProvider htmlrender = Mockito.mock(VideoProvider.class);
        VideoProvider painted = Mockito.mock(VideoProvider.class);
        VideoProvider hyperframes = Mockito.mock(VideoProvider.class);

        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(ctx.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);
        when(ctx.getBean("novAiVideoProvider", VideoProvider.class)).thenReturn(novai);
        when(ctx.getBean("doubaoEmailVideoProvider", VideoProvider.class)).thenReturn(doubao);
        when(ctx.getBean("htmlRenderVideoProvider", VideoProvider.class)).thenReturn(htmlrender);
        when(ctx.getBean("paintedAnimationVideoProvider", VideoProvider.class)).thenReturn(painted);
        when(ctx.getBean("hyperFramesVideoProvider", VideoProvider.class)).thenReturn(hyperframes);

        when(agnes.submit(nullable(Shot.class), anyInt())).thenThrow(new RuntimeException("boom"));
        when(minimax.submit(nullable(Shot.class), anyInt())).thenThrow(new RuntimeException("boom"));
        when(novai.submit(nullable(Shot.class), anyInt())).thenThrow(new RuntimeException("boom"));
        when(doubao.submit(nullable(Shot.class), anyInt())).thenThrow(new RuntimeException("boom"));
        when(htmlrender.submit(nullable(Shot.class), anyInt())).thenThrow(new RuntimeException("boom"));
        when(painted.submit(nullable(Shot.class), anyInt())).thenThrow(new RuntimeException("boom"));
        when(hyperframes.submit(nullable(Shot.class), anyInt())).thenThrow(new RuntimeException("boom"));

        VideoProviderRouter router = new VideoProviderRouter(ctx, env, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> router.submit(null, 5));
        assertTrue(ex.getMessage().startsWith("所有视频通道均失败"));

        verify(agnes, times(1)).submit(nullable(Shot.class), eq(5));
        verify(minimax, times(1)).submit(nullable(Shot.class), eq(5));
        verify(novai, times(1)).submit(nullable(Shot.class), eq(5));
        verify(doubao, times(1)).submit(nullable(Shot.class), eq(5));
        verify(htmlrender, times(1)).submit(nullable(Shot.class), eq(5));
        verify(painted, times(1)).submit(nullable(Shot.class), eq(5));
        verify(hyperframes, times(1)).submit(nullable(Shot.class), eq(5));
    }

    // ---------- C2 首个 429 降级 ----------

    @Test
    void submitFirstRateLimitedFallsToSecond() {
        // 第 1 个 agnes 抛 RateLimitedException(限流, 30)，第 2 个 minimax 返回 "task-9"。
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");

        ApplicationContext ctx = Mockito.mock(ApplicationContext.class);
        VideoProvider agnes = Mockito.mock(VideoProvider.class);
        VideoProvider minimax = Mockito.mock(VideoProvider.class);
        when(ctx.getBean("agnesVideoProvider", VideoProvider.class)).thenReturn(agnes);
        when(ctx.getBean("miniMaxH3VideoProvider", VideoProvider.class)).thenReturn(minimax);

        when(agnes.submit(nullable(Shot.class), anyInt()))
                .thenThrow(new RateLimitedException("限流", 30));
        when(minimax.submit(nullable(Shot.class), anyInt())).thenReturn("task-9");

        VideoProviderRouter router = new VideoProviderRouter(ctx, env, null);
        VideoProviderRouter.RouteResult result = router.submit(null, 5);

        assertEquals("minimax", result.providerName());
        assertEquals("task-9", result.providerTaskId());
        assertNotNull(result.fallbackReason());
        assertTrue(result.fallbackReason().contains("限流(429)"));
        assertNotNull(router.lastFallback());
        assertEquals("agnes", router.lastFallback().from());
    }

    // ---------- C3 routeWithScores 决策记录 ----------

    @Test
    void routeWithScoresEmptyScoresSelectsChainHead() {
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProviderRouter router = new VideoProviderRouter(null, env, null);

        RoutingDecision decision = router.routeWithScores(null, Map.of(), "测试");
        assertEquals("agnes", decision.selected());

        List<RoutingDecision> recent = router.recentDecisions();
        assertTrue(recent.contains(decision));
    }

    @Test
    void routeWithScoresPicksHighestScoredProvider() {
        // minimax 全 1 → 加权分 1.0，agnes 全 0 → 0.0；minimax 应被选中。
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProviderRouter router = new VideoProviderRouter(null, env, null);

        Map<String, ProviderScoreCard> scores = new LinkedHashMap<>();
        scores.put("agnes", new ProviderScoreCard(0, 0, 0, 0, 0, 0, 0));
        scores.put("minimax", new ProviderScoreCard(1, 1, 1, 1, 1, 1, 1));

        RoutingDecision decision = router.routeWithScores(null, scores, "测试");
        assertEquals("minimax", decision.selected());
    }

    @Test
    void routeWithScoresRecentDecisionsNewestFirst() {
        // 连续两次调用，recentDecisions().get(0) 应是第二次的决策（新到旧）。
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn("agnes");
        VideoProviderRouter router = new VideoProviderRouter(null, env, null);

        RoutingDecision first = router.routeWithScores(null, Map.of(), "第一次");
        RoutingDecision second = router.routeWithScores(null, Map.of(), "第二次");

        List<RoutingDecision> recent = router.recentDecisions();
        assertSame(second, recent.get(0));
        assertSame(first, recent.get(1));
    }
}
