package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PromptLibraryServicePaginationValidationTest {

    @Test
    void negativePageThrows() {
        PromptLibraryService service = new PromptLibraryService();
        IllegalArgumentException exception = assertThrows(IllegalArgumentException.class,
                () -> service.list(null, null, -1, 20));
        assertEquals("page 参数非法", exception.getMessage());
    }

    @Test
    void zeroSizeThrows() {
        PromptLibraryService service = new PromptLibraryService();
        IllegalArgumentException exception = assertThrows(IllegalArgumentException.class,
                () -> service.list(null, null, 0, 0));
        assertEquals("size 参数非法", exception.getMessage());
    }

    @Test
    void negativeSizeThrows() {
        PromptLibraryService service = new PromptLibraryService();
        IllegalArgumentException exception = assertThrows(IllegalArgumentException.class,
                () -> service.list(null, null, 0, -5));
        assertEquals("size 参数非法", exception.getMessage());
    }

    @Test
    void oversizeSizeThrows() {
        PromptLibraryService service = new PromptLibraryService();
        IllegalArgumentException exception = assertThrows(IllegalArgumentException.class,
                () -> service.list(null, null, 0, 101));
        assertEquals("size 参数非法", exception.getMessage());
    }

    @Test
    void sizeOneOk() {
        PromptLibraryService service = new PromptLibraryService();
        var result = service.list(null, null, 0, 1);
        assertEquals(1, result.size());
    }

    @Test
    void sizeHundredOk() {
        PromptLibraryService service = new PromptLibraryService();
        var result = service.list(null, null, 0, 100);
        assertEquals(100, result.size());
    }

    @Test
    void pageZeroOk() {
        PromptLibraryService service = new PromptLibraryService();
        var result = service.list(null, null, 0, 20);
        assertEquals(0, result.page());
    }
}