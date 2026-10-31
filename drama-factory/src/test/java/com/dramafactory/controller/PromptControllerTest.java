package com.dramafactory.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.dramafactory.service.prompt.PromptLibraryService;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

class PromptControllerTest {

    private PromptController controller;

    @BeforeEach
    void setUp() {
        controller = new PromptController(new PromptLibraryService());
    }

    @Test
    void listReturnsAll() {
        ResponseEntity<List<PromptController.PromptSummaryDto>> response = controller.list(null);
        assertEquals(200, response.getStatusCode().value());
        List<PromptController.PromptSummaryDto> body = response.getBody();
        assertNotNull(body);
        int expected = (int) new PromptLibraryService().list(null, null, 0, 100).totalElements();
        assertEquals(expected, body.size());
    }

    @Test
    void listSearchNarrows() {
        ResponseEntity<List<PromptController.PromptSummaryDto>> response = controller.list("雨爱");
        assertEquals(200, response.getStatusCode().value());
        List<PromptController.PromptSummaryDto> body = response.getBody();
        assertNotNull(body);
        assertFalse(body.isEmpty());
        for (PromptController.PromptSummaryDto dto : body) {
            assertTrue(dto.title().contains("雨爱") || dto.summary().contains("雨爱"));
        }
    }

    @Test
    void detailFound() {
        ResponseEntity<PromptController.PromptDetailDto> response =
                controller.detail("yuai-deepseek-prompt");
        assertEquals(200, response.getStatusCode().value());
        PromptController.PromptDetailDto body = response.getBody();
        assertNotNull(body);
        assertEquals("DeepSeek 做《雨爱》MV 的提示词（部分转录）", body.title());
        assertNotNull(body.content());
        assertFalse(body.content().isEmpty());
    }

    @Test
    void detailMissingIs404() {
        ResponseEntity<PromptController.PromptDetailDto> response = controller.detail("no-such-id");
        assertEquals(404, response.getStatusCode().value());
    }
}
