package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class PromptLibraryServiceSortAndIndexTest {

    @Test
    void getRoundTripForEveryListedId() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertFalse(summaries.isEmpty());
        for (PromptLibraryService.PromptSummary summary : summaries) {
            Optional<PromptLibraryService.PromptDetail> detailOpt = service.get(summary.id());
            assertTrue(detailOpt.isPresent(), "get should return present for id: " + summary.id());
            PromptLibraryService.PromptDetail detail = detailOpt.get();
            assertEquals(summary.id(), detail.id());
            assertEquals(summary.title(), detail.title());
            assertEquals(summary.source(), detail.source());
            assertEquals(summary.path(), detail.path());
            assertEquals(summary.summary(), detail.summary());
            assertNotNull(detail.content());
            assertFalse(detail.content().isEmpty());
        }
    }

    @Test
    void getUnknownAndEmptyIdReturnsEmpty() {
        PromptLibraryService service = new PromptLibraryService();
        assertTrue(service.get("this-id-does-not-exist-zzz").isEmpty());
        assertTrue(service.get("").isEmpty());
        assertTrue(service.get(null).isEmpty());
        assertTrue(service.get("YUAI-DEEPSEEK-PROMPT").isEmpty());
    }

    @Test
    void listNullEqualsListEmptyString() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> nullList = service.list(null);
        List<PromptLibraryService.PromptSummary> emptyList = service.list("");
        assertFalse(nullList.isEmpty());
        assertFalse(emptyList.isEmpty());
        assertEquals(nullList.size(), emptyList.size());
        for (int i = 0; i < nullList.size(); i++) {
            assertEquals(nullList.get(i).id(), emptyList.get(i).id());
        }
    }

    @Test
    void idBuildRuleSpotCheck() {
        PromptLibraryService service = new PromptLibraryService();
        assertTrue(service.get("yuai-deepseek-prompt").isPresent());
        assertTrue(service.get("opus-video-prompts__prompts__01-inference-startup-launch").isPresent());
        assertTrue(service.get("pdoom-video__STORYBOARD").isPresent());
        assertTrue(service.get("pdoom-video__README-archive-note").isPresent());

        List<PromptLibraryService.PromptSummary> all = service.list(null);
        for (PromptLibraryService.PromptSummary summary : all) {
            assertFalse(summary.id().endsWith(".md"), "id should not end with .md: " + summary.id());
            assertFalse(summary.id().contains("/"), "id should not contain /: " + summary.id());
        }
    }

    @Test
    void sourceRuleSpotCheck() {
        PromptLibraryService service = new PromptLibraryService();
        assertEquals("根目录", service.get("yuai-deepseek-prompt").get().source());
        assertEquals("opus-video-prompts", service.get("opus-video-prompts__prompts__01-inference-startup-launch").get().source());
        assertEquals("pdoom-video", service.get("pdoom-video__STORYBOARD").get().source());
        assertEquals("根目录", service.get("README").get().source());
    }

    @Test
    void listKeywordIsCaseInsensitiveAndTrimmed() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> trimmed = service.list("  雨爱  ");
        List<PromptLibraryService.PromptSummary> normal = service.list("雨爱");
        assertFalse(trimmed.isEmpty());
        assertFalse(normal.isEmpty());
        assertEquals(normal.size(), trimmed.size());
        for (int i = 0; i < normal.size(); i++) {
            assertEquals(normal.get(i).id(), trimmed.get(i).id());
        }
        assertTrue(trimmed.stream().anyMatch(s -> s.id().equals("yuai-deepseek-prompt")));

        List<PromptLibraryService.PromptSummary> storyboard = service.list("STORYBOARD");
        assertFalse(storyboard.isEmpty());
        assertTrue(storyboard.stream().anyMatch(s -> s.id().equals("pdoom-video__STORYBOARD")));
    }

    @Test
    void listResultOrderMatchesPathSort() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertFalse(summaries.isEmpty());
        String previousPath = null;
        for (PromptLibraryService.PromptSummary summary : summaries) {
            if (previousPath != null) {
                assertTrue(previousPath.compareTo(summary.path()) <= 0, "path should be non-decreasing: " + previousPath + " > " + summary.path());
            }
            previousPath = summary.path();

            Optional<PromptLibraryService.PromptDetail> detailOpt = service.get(summary.id());
            assertTrue(detailOpt.isPresent());
            assertEquals(summary.path(), detailOpt.get().path());
        }
    }

    @Test
    void listNoMatchReturnsEmpty() {
        PromptLibraryService service = new PromptLibraryService();
        assertTrue(service.list("zzzz-no-such-word-qqq").isEmpty());
    }
}