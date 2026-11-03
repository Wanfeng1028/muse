package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

public class PromptLibraryServiceTagTest {

    private final PromptLibraryService service = new PromptLibraryService();

    @Test
    void tagsNotEmpty() {
        List<String> tags = service.tags();
        assertFalse(tags.isEmpty());
    }

    @Test
    void tagsSorted() {
        List<String> tags = service.tags();
        for (int i = 0; i < tags.size() - 1; i++) {
            assertTrue(tags.get(i).compareTo(tags.get(i + 1)) <= 0);
        }
    }

    @Test
    void tagsContainKnownSources() {
        List<String> tags = service.tags();
        assertTrue(tags.contains("根目录"));
        assertTrue(tags.contains("opus-video-prompts"));
        assertTrue(tags.contains("pdoom-video"));
    }

    @Test
    void tagsAreDistinct() {
        List<String> tags = service.tags();
        Set<String> unique = new HashSet<>(tags);
        assertEquals(unique.size(), tags.size());
    }

    @Test
    void tagExactMatch() {
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, "opus-video-prompts", 0, 100);
        assertEquals(19L, page.totalElements());
        assertFalse(page.content().isEmpty());
        for (PromptLibraryService.PromptSummary summary : page.content()) {
            assertEquals("opus-video-prompts", summary.source());
        }
    }

    @Test
    void tagCaseSensitive() {
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, "OPUS-VIDEO-PROMPTS", 0, 100);
        assertTrue(page.content().isEmpty());
        assertEquals(0L, page.totalElements());
    }

    @Test
    void unknownTagEmpty() {
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, "no-such-source", 0, 10);
        assertTrue(page.content().isEmpty());
        assertEquals(0L, page.totalElements());
    }

    @Test
    void qAndTagCombined() {
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list("AI", "根目录", 0, 100);
        assertFalse(page.content().isEmpty());
        for (PromptLibraryService.PromptSummary summary : page.content()) {
            assertEquals("根目录", summary.source());
            String title = summary.title() == null ? "" : summary.title().toLowerCase(Locale.ROOT);
            String summaryText = summary.summary() == null ? "" : summary.summary().toLowerCase(Locale.ROOT);
            assertTrue(title.contains("ai") || summaryText.contains("ai"));
        }
    }
}
