package com.dramafactory.service.video;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import com.dramafactory.service.video.ProviderScoringService.LatencyClass;
import com.dramafactory.service.video.ProviderScoringService.ProviderCandidate;
import com.dramafactory.service.video.ProviderScoringService.ScoredProvider;
import com.dramafactory.service.video.ProviderScoringService.TaskContext;

class ProviderScoringServiceTest {

    private final ProviderScoringService service = new ProviderScoringService();

    @Test
    void rankSortsDescendingByWeightedScore() {
        ProviderCandidate strong = new ProviderCandidate(
                "agnes",
                Set.of("video", "motion", "clip", "cinematic"),
                0.05,
                0.95,
                0.95,
                Set.of("referenceImage", "cameraControl", "styleTransfer"),
                LatencyClass.FAST,
                true);

        ProviderCandidate weak = new ProviderCandidate(
                "painted",
                Set.of("still", "painting"),
                0.9,
                0.4,
                0.4,
                Set.of("seed"),
                LatencyClass.SLOW,
                false);

        TaskContext context = new TaskContext(
                "cinematic motion clip for hero video",
                Set.of("cinematic", "motion"),
                5.0,
                5.0,
                0.8,
                Set.of(),
                true,
                "video");

        List<ScoredProvider> result = service.rank(List.of(weak, strong), context);

        assertEquals(2, result.size());
        assertEquals("agnes", result.get(0).providerName());
        assertEquals("painted", result.get(1).providerName());
        assertTrue(result.get(0).weightedScore() > result.get(1).weightedScore());
    }

    @Test
    void weightedScoreMatchesManualComputation() {
        ProviderCandidate candidate = new ProviderCandidate(
                "minimax",
                Set.of("video", "motion"),
                0.10,
                0.80,
                0.90,
                Set.of("referenceImage", "styleTransfer"),
                LatencyClass.MEDIUM,
                false);

        TaskContext context = new TaskContext(
                "video motion",
                Set.of(),
                10.0,
                10.0,
                0.7,
                Set.of("minimax"),
                true,
                "video");

        ScoredProvider scored = service.rank(List.of(candidate), context).get(0);
        var dims = scored.dimensions();

        double expected = Math.round((dims.get("taskFit") * 0.30
                + dims.get("quality") * 0.20
                + dims.get("control") * 0.15
                + dims.get("reliability") * 0.15
                + dims.get("costEfficiency") * 0.10
                + dims.get("latency") * 0.05
                + dims.get("continuity") * 0.05) * 10000.0) / 10000.0;

        assertEquals(expected, scored.weightedScore(), 1e-9);
    }

    @Test
    void overBudgetCandidateGetsZeroCostEfficiencyAndReason() {
        ProviderCandidate expensive = new ProviderCandidate(
                "doubao",
                Set.of("video", "motion"),
                12.0,
                0.9,
                0.9,
                Set.of("referenceImage"),
                LatencyClass.FAST,
                true);

        TaskContext context = new TaskContext(
                "video motion",
                Set.of(),
                5.0,
                5.0,
                0.8,
                Set.of(),
                true,
                "video");

        ScoredProvider scored = service.rank(List.of(expensive), context).get(0);

        assertEquals(0.0, scored.dimensions().get("costEfficiency"), 1e-9);
        assertTrue(scored.reasons().stream().anyMatch(r -> r.contains("超出预算")));
    }

    @Test
    void continuityHigherForLockedProvider() {
        ProviderCandidate locked = new ProviderCandidate(
                "novai",
                Set.of("video", "motion"),
                0.10,
                0.8,
                0.8,
                Set.of("referenceImage"),
                LatencyClass.MEDIUM,
                false);

        ProviderCandidate unlocked = new ProviderCandidate(
                "htmlrender",
                Set.of("video", "motion"),
                0.10,
                0.8,
                0.8,
                Set.of("referenceImage"),
                LatencyClass.MEDIUM,
                false);

        TaskContext context = new TaskContext(
                "video motion",
                Set.of(),
                10.0,
                10.0,
                0.7,
                Set.of("novai"),
                true,
                "video");

        List<ScoredProvider> result = service.rank(List.of(locked, unlocked), context);
        ScoredProvider lockedScored = result.stream()
                .filter(s -> s.providerName().equals("novai"))
                .findFirst()
                .orElseThrow();
        ScoredProvider unlockedScored = result.stream()
                .filter(s -> s.providerName().equals("htmlrender"))
                .findFirst()
                .orElseThrow();

        assertTrue(lockedScored.dimensions().get("continuity") > unlockedScored.dimensions().get("continuity"));
    }

    @Test
    void emptyCandidateListReturnsEmptyList() {
        TaskContext context = new TaskContext(
                "video motion",
                Set.of(),
                10.0,
                10.0,
                0.7,
                Set.of(),
                true,
                "video");

        List<ScoredProvider> result = service.rank(List.of(), context);

        assertNotNull(result);
        assertTrue(result.isEmpty());
    }

    @Test
    void reasonsAreNonEmptyForEveryScoredProvider() {
        ProviderCandidate a = new ProviderCandidate(
                "agnes",
                Set.of("video", "motion"),
                0.05,
                0.9,
                0.9,
                Set.of("referenceImage", "cameraControl"),
                LatencyClass.FAST,
                true);

        ProviderCandidate b = new ProviderCandidate(
                "painted",
                Set.of("still", "painting"),
                0.5,
                0.5,
                0.5,
                Set.of(),
                LatencyClass.SLOW,
                false);

        TaskContext context = new TaskContext(
                "cinematic motion clip",
                Set.of("cinematic"),
                10.0,
                10.0,
                0.8,
                Set.of(),
                true,
                "video");

        List<ScoredProvider> result = service.rank(List.of(a, b), context);

        assertEquals(2, result.size());
        for (ScoredProvider scored : result) {
            assertNotNull(scored.reasons());
            assertFalse(scored.reasons().isEmpty());
        }
    }
}
