package com.dramafactory.service.prompt;

import static org.junit.jupiter.api.Assertions.*;
import java.util.Locale;

class PromptLibraryPagingRestTest {

    @org.junit.jupiter.api.Test
    void totalPages_Math() {
        PromptLibraryService service = new PromptLibraryService();
        long total = service.list(null, null, 0, 20).totalElements();
        assertTrue(total > 0);
        assertEquals((total + 20 - 1) / 20, service.list(null, null, 0, 20).totalPages());
        assertEquals(total, service.list(null, null, 0, 1).totalPages());
    }

    @org.junit.jupiter.api.Test
    void secondPage_NoOverlapWithFirst() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> a = service.list(null, null, 0, 1);
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> b = service.list(null, null, 1, 1);
        assertFalse(a.content().isEmpty());
        if (!b.content().isEmpty()) {
            assertNotEquals(a.content().get(0).id(), b.content().get(0).id());
        }
    }

    @org.junit.jupiter.api.Test
    void tagFilter_CaseSensitive() {
        PromptLibraryService service = new PromptLibraryService();
        String tag = service.tags().get(0);
        assertEquals(0, service.list(null, tag.toUpperCase(Locale.ROOT), 0, 20).totalElements());
        assertTrue(service.list(null, tag, 0, 20).totalElements() > 0);
    }

    @org.junit.jupiter.api.Test
    void keywordSearch_NarrowsResults() {
        PromptLibraryService service = new PromptLibraryService();
        long all = service.list(null, null, 0, 20).totalElements();
        long sub = service.list("yuai", null, 0, 20).totalElements();
        assertTrue(sub < all);
        for (PromptLibraryService.PromptSummary p : service.list("yuai", null, 0, 20).content()) {
            assertTrue(p.title().toLowerCase().contains("yuai") || p.summary().toLowerCase().contains("yuai"));
        }
    }
}
