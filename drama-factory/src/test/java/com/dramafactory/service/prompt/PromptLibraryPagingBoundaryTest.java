package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class PromptLibraryPagingBoundaryTest {

    @Test
    void negativePage_NormalizedToZero() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> negativePage = service.list(null, null, -1, 20);
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> zeroPage = service.list(null, null, 0, 20);
        
        assertEquals(0, negativePage.page());
        assertEquals(zeroPage.content().size(), negativePage.content().size());
        for (int i = 0; i < zeroPage.content().size(); i++) {
            assertEquals(zeroPage.content().get(i).id(), negativePage.content().get(i).id());
        }
    }

    @Test
    void zeroSize_DefaultsTo20() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, null, 0, 0);
        assertEquals(20, page.size());
    }

    @Test
    void oversizeSize_ClampedTo100() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, null, 0, 500);
        assertEquals(100, page.size());
    }

    @Test
    void pageBeyondTotal_EmptyContent() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> first = service.list(null, null, 0, 20);
        int totalPages = first.totalPages();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> beyond = service.list(null, null, totalPages, 20);
        
        assertTrue(beyond.content().isEmpty());
        assertEquals(first.totalElements(), beyond.totalElements());
    }
}
