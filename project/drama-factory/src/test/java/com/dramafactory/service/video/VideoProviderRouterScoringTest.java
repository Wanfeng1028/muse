package com.dramafactory.service.video;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public class VideoProviderRouterScoringTest {

    private VideoProviderRouter createRouter(String preferred) {
        Environment env = mock(Environment.class);
        when(env.getProperty("drama.video.provider", "mock")).thenReturn(preferred);
        ApplicationContext ctx = mock(ApplicationContext.class);
        ShotVideoRouter shotVideoRouter = mock(ShotVideoRouter.class);
        return new VideoProviderRouter(ctx, env, shotVideoRouter);
    }

    @Test
    void weightsSumToOne() {
        double sum = ProviderScoreCard.W_TASK_FIT
                + ProviderScoreCard.W_OUTPUT_QUALITY
                + ProviderScoreCard.W_CONTROL
                + ProviderScoreCard.W_RELIABILITY
                + ProviderScoreCard.W_COST_EFFICIENCY
                + ProviderScoreCard.W_LATENCY
                + ProviderScoreCard.W_CONTINUITY;
        assertEquals(1.0, sum, 1e-9);
    }

    @Test
    void controlOnlyYieldsPointFifteen() {
        ProviderScoreCard card = new ProviderScoreCard(0, 0, 1.0, 0, 0, 0, 0);
        assertEquals(0.15, card.weightedScore(), 1e-9);
    }

    @Test
    void reliabilityOnlyYieldsPointFifteen() {
        ProviderScoreCard card = new ProviderScoreCard(0, 0, 0, 1.0, 0, 0, 0);
        assertEquals(0.15, card.weightedScore(), 1e-9);
    }

    @Test
    void costEfficiencyOnlyYieldsPointOneZero() {
        ProviderScoreCard card = new ProviderScoreCard(0, 0, 0, 0, 1.0, 0, 0);
        assertEquals(0.10, card.weightedScore(), 1e-9);
    }

    @Test
    void latencyOnlyYieldsPointZeroFive() {
        ProviderScoreCard card = new ProviderScoreCard(0, 0, 0, 0, 0, 1.0, 0);
        assertEquals(0.05, card.weightedScore(), 1e-9);
    }

    @Test
    void continuityOnlyYieldsPointZeroFive() {
        ProviderScoreCard card = new ProviderScoreCard(0, 0, 0, 0, 0, 0, 1.0);
        assertEquals(0.05, card.weightedScore(), 1e-9);
    }

    @Test
    void allZerosYieldsZero() {
        ProviderScoreCard card = new ProviderScoreCard(0, 0, 0, 0, 0, 0, 0);
        assertEquals(0.0, card.weightedScore(), 1e-9);
    }

    @Test
    void mixedDimensionsExactMath() {
        ProviderScoreCard card = new ProviderScoreCard(1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5);
        assertEquals(0.65, card.weightedScore(), 1e-9);
    }

    @Test
    void boundaryZeroAndOneAreValid() {
        ProviderScoreCard zeros = new ProviderScoreCard(0, 0, 0, 0, 0, 0, 0);
        assertEquals(0.0, zeros.weightedScore(), 1e-9);
        ProviderScoreCard ones = new ProviderScoreCard(1, 1, 1, 1, 1, 1, 1);
        assertEquals(1.0, ones.weightedScore(), 1e-9);
    }

    @Test
    void explainListsTopContributorFirst() {
        ProviderScoreCard card = new ProviderScoreCard(1.0, 0, 0, 0, 0, 0, 0);
        String explain = card.explain();
        assertTrue(explain.contains("1) taskFit"));
    }

    @Test
    void gettersReturnConstructedValues() {
        ProviderScoreCard card = new ProviderScoreCard(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7);
        assertEquals(0.1, card.taskFit(), 1e-9);
        assertEquals(0.2, card.outputQuality(), 1e-9);
        assertEquals(0.3, card.control(), 1e-9);
        assertEquals(0.4, card.reliability(), 1e-9);
        assertEquals(0.5, card.costEfficiency(), 1e-9);
        assertEquals(0.6, card.latency(), 1e-9);
        assertEquals(0.7, card.continuity(), 1e-9);
    }

    @Test
    void nullScoreCardsBehavesLikeChain() {
        VideoProviderRouter router = createRouter("agnes");
        assertEquals(router.chain(null), router.rankedChain(null, null));
    }

    @Test
    void emptyScoreCardsBehavesLikeChain() {
        VideoProviderRouter router = createRouter("agnes");
        assertEquals(router.chain(null), router.rankedChain(null, Map.of()));
    }

    @Test
    void scoredProvidersSortedDescendingUnscoredKeepBaseOrder() {
        VideoProviderRouter router = createRouter("agnes");
        Map<String, ProviderScoreCard> scoreCards = new HashMap<>();
        scoreCards.put("agnes", new ProviderScoreCard(0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9));
        scoreCards.put("minimax", new ProviderScoreCard(0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8));
        scoreCards.put("novai", new ProviderScoreCard(0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7));
        List<String> ranked = router.rankedChain(null, scoreCards);
        assertEquals(List.of("agnes", "minimax", "novai", "doubao", "hyperframes", "htmlrender", "painted"), ranked);
    }

    @Test
    void cardsForUnknownProvidersIgnored() {
        VideoProviderRouter router = createRouter("agnes");
        Map<String, ProviderScoreCard> scoreCards = new HashMap<>();
        scoreCards.put("qwen", new ProviderScoreCard(0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9));
        assertEquals(router.chain(null), router.rankedChain(null, scoreCards));
    }

    @Test
    void tieScoresKeepBaseOrder() {
        VideoProviderRouter router = createRouter("agnes");
        Map<String, ProviderScoreCard> scoreCards = new HashMap<>();
        scoreCards.put("minimax", new ProviderScoreCard(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5));
        scoreCards.put("novai", new ProviderScoreCard(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5));
        List<String> ranked = router.rankedChain(null, scoreCards);
        assertTrue(ranked.indexOf("minimax") < ranked.indexOf("novai"));
    }

    @Test
    void routeWithScoresSelectsTopCandidateAndLogsDecision() {
        VideoProviderRouter router = createRouter("agnes");
        Map<String, ProviderScoreCard> scoreCards = new HashMap<>();
        scoreCards.put("agnes", new ProviderScoreCard(0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9));
        scoreCards.put("minimax", new ProviderScoreCard(0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1));
        RoutingDecision decision = router.routeWithScores(null, scoreCards, "test-reason");
        assertEquals("agnes", decision.selected());
        assertEquals(2, decision.scores().size());
        assertEquals(1, router.recentDecisions().size());
        assertEquals("test-reason", decision.reason());
        assertNull(decision.shotId());
    }

    @Test
    void decisionLogEvictsOldestBeyondFifty() {
        VideoProviderRouter router = createRouter("agnes");
        for (int i = 0; i < 55; i++) {
            router.routeWithScores(null, Map.of(), "reason-" + i);
        }
        List<RoutingDecision> decisions = router.recentDecisions();
        assertEquals(50, decisions.size());
        assertFalse(decisions.get(0).decidedAt().isBefore(decisions.get(49).decidedAt()));
    }

    @Test
    void mockPreferredYieldsSingleMockChain() {
        VideoProviderRouter router = createRouter("mock");
        assertEquals(List.of("mock"), router.chain(null));
    }

    @Test
    void blankPreferredFallsBackToMock() {
        VideoProviderRouter router = createRouter("");
        assertEquals(List.of("mock"), router.chain(null));
    }
}