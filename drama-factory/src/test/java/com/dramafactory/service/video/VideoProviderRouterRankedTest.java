package com.dramafactory.service.video;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.core.env.Environment;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

/**
 * VideoProviderRouter 打分排序相关单测，仅 mock Environment。
 */
class VideoProviderRouterRankedTest {

    /** 构造一个仅用于排序测试的 router。 */
    private VideoProviderRouter newRouter(String defaultProvider) {
        Environment env = Mockito.mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn(defaultProvider);
        return new VideoProviderRouter(null, env, null);
    }

    /** 生成一张指定维度打分的卡片，参数顺序：taskFit, outputQuality。 */
    private static ProviderScoreCard scoreCard(double taskFit, double outputQuality) {
        return new ProviderScoreCard(taskFit, outputQuality, 0.0, 0.0, 0.0, 0.0, 0.0);
    }

    /** rankedChain 应按加权分降序排列，其余无分通道保持 DEFAULT_ORDER。 */
    @Test
    void rankedChainDescending() {
        VideoProviderRouter router = newRouter("agnes");

        Map<String, ProviderScoreCard> scores = new LinkedHashMap<>();
        // agnes taskFit=1.0 权重 0.30 -> 0.30
        // minimax outputQuality=1.0 权重 0.20 -> 0.20
        // novai 全 0 -> 0.0
        scores.put("agnes", scoreCard(1.0, 0.0));
        scores.put("minimax", scoreCard(0.0, 1.0));
        scores.put("novai", scoreCard(0.0, 0.0));

        List<String> chain = router.rankedChain(null, scores);
        assertEquals(
                List.of("agnes", "minimax", "novai", "doubao", "htmlrender", "painted"),
                chain);
    }

    /** 无打分卡通道排最后且保持原有顺序。 */
    @Test
    void unscoredKeepOriginalOrderAtEnd() {
        VideoProviderRouter router = newRouter("agnes");

        Map<String, ProviderScoreCard> scores = new LinkedHashMap<>();
        scores.put("agnes", scoreCard(0.0, 1.0));

        List<String> chain = router.rankedChain(null, scores);

        // agnes 有分排最前，其余无分保持 DEFAULT_ORDER 原顺序
        assertEquals("agnes", chain.get(0));
        assertEquals(6, chain.size());
        assertEquals(
                List.of("minimax", "novai", "doubao", "htmlrender", "painted"),
                chain.subList(1, 6));
    }

    /** 空打分 map 时，rankedChain 应与 chain(null) 一致。 */
    @Test
    void emptyScoresMatchChainNull() {
        VideoProviderRouter router = newRouter("agnes");

        List<String> ranked = router.rankedChain(null, Collections.emptyMap());
        List<String> plain = router.chain(null);
        assertEquals(plain, ranked);
    }

    /** routeWithScores 选中最高分通道，并写入 recentDecisions。 */
    @Test
    void routeWithScoresSelectsTopAndRecords() {
        VideoProviderRouter router = newRouter("agnes");

        Map<String, ProviderScoreCard> scores = new LinkedHashMap<>();
        // minimax taskFit=1.0 权重 0.30 -> 0.30 最高
        scores.put("agnes", scoreCard(0.0, 0.0));
        scores.put("minimax", scoreCard(1.0, 0.0));
        scores.put("novai", scoreCard(0.0, 1.0));

        RoutingDecision decision = router.routeWithScores(null, scores, "test");
        assertNotNull(decision);
        assertEquals("minimax", decision.selected());

        List<RoutingDecision> recent = router.recentDecisions();
        assertTrue(recent.contains(decision), "recentDecisions 应包含刚产生的决策");
    }
}