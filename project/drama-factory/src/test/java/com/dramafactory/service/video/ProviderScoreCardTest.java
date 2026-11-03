package com.dramafactory.service.video;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * ProviderScoreCard 七维加权打分单测。
 */
class ProviderScoreCardTest {

    /** 全部维度取 1.0 时，加权总分应为 1.0。 */
    @Test
    void allOnesYieldsOne() {
        ProviderScoreCard card = new ProviderScoreCard(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0);
        assertEquals(1.0, card.weightedScore(), 1e-9);
    }

    /** 仅 taskFit 为 1，其余为 0，权重 0.30。 */
    @Test
    void taskFitOnlyWeighsThirtyPercent() {
        ProviderScoreCard card = new ProviderScoreCard(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
        assertEquals(0.30, card.weightedScore(), 1e-9);
    }

    /** 仅 outputQuality 为 1，其余为 0，权重 0.20。 */
    @Test
    void outputQualityOnlyWeighsTwentyPercent() {
        ProviderScoreCard card = new ProviderScoreCard(0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0);
        assertEquals(0.20, card.weightedScore(), 1e-9);
    }

    /** 越界值（小于 0）应抛 IllegalArgumentException。 */
    @Test
    void belowZeroThrows() {
        assertThrows(IllegalArgumentException.class,
                () -> new ProviderScoreCard(-0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0));
    }

    /** 越界值（大于 1）应抛 IllegalArgumentException。 */
    @Test
    void aboveOneThrows() {
        assertThrows(IllegalArgumentException.class,
                () -> new ProviderScoreCard(1.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0));
    }

    /** NaN 应抛 IllegalArgumentException。 */
    @Test
    void nanThrows() {
        assertThrows(IllegalArgumentException.class,
                () -> new ProviderScoreCard(Double.NaN, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0));
    }

    /** explain() 应包含加权总分数字。 */
    @Test
    void explainContainsWeightedScore() {
        ProviderScoreCard card = new ProviderScoreCard(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
        String text = card.explain();
        assertTrue(text.contains("0.30"), "explain 应包含加权总分 0.30，实际: " + text);
    }
}
