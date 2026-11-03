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
        IllegalArgumentException exception = assertThrows(IllegalArgumentException.class, () -> service.list(null, null, -1, 20));
        assertEquals("page 参数非法", exception.getMessage());
    }

    @Test
    void zeroSize_DefaultsTo20() {
        PromptLibraryService service = new PromptLibraryService();
        IllegalArgumentException exception = assertThrows(IllegalArgumentException.class, () -> service.list(null, null, 0, 0));
        assertEquals("size 参数非法", exception.getMessage());
    }

    @Test
    void oversizeSize_ClampedTo100() {
        PromptLibraryService service = new PromptLibraryService();
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () -> service.list(null, null, 0, 500));
        assertEquals("size 参数非法", ex.getMessage());
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
