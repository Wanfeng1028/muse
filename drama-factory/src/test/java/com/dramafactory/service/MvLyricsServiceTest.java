package com.dramafactory.service;

import com.dramafactory.service.LlmScriptService.ModelCallResult;
import com.dramafactory.service.MvLyricsService.LyricSection;
import com.dramafactory.service.MvLyricsService.LyricsResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

class MvLyricsServiceTest {

    private LlmScriptService llmScriptService;
    private MvLyricsService service;
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        llmScriptService = org.mockito.Mockito.mock(LlmScriptService.class);
        service = new MvLyricsService(objectMapper, llmScriptService);
    }

    private void stubContent(String content) {
        when(llmScriptService.callModelWithUsage(any(ObjectNode.class)))
                .thenReturn(new ModelCallResult(content, 11L, 22L));
    }

    @Test
    void generateParsesNormalResult() {
        stubContent("{\"title\":\"T\",\"sections\":[{\"name\":\"verse\",\"mood\":\"calm\",\"lyrics\":\"la la\",\"estSeconds\":30}]}");
        LyricsResult result = service.generate("theme", "mood", "style");
        assertEquals(1, result.sections().size());
        LyricSection s = result.sections().get(0);
        assertEquals("verse", s.name());
        assertEquals("calm", s.mood());
        assertEquals("la la", s.lyrics());
        assertEquals(30, s.estSeconds());
    }

    @Test
    void generatePassesThroughTokens() {
        stubContent("{\"title\":\"T\",\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\"}]}");
        LyricsResult result = service.generate("theme", "mood", "style");
        assertEquals(11L, result.promptTokens());
        assertEquals(22L, result.completionTokens());
    }

    @Test
    void generateStripsCodeFence() {
        stubContent("```json\n{\"title\":\"T\",\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\"}]}\n```");
        LyricsResult result = service.generate("theme", "mood", "style");
        assertEquals(1, result.sections().size());
        assertEquals("x", result.sections().get(0).lyrics());
    }

    @Test
    void generateThrowsOnInvalidJson() {
        stubContent("not a json at all");
        assertThrows(IllegalStateException.class, () -> service.generate("theme", "mood", "style"));
    }

    @Test
    void generateThrowsOnEmptySectionsArray() {
        stubContent("{\"title\":\"T\",\"sections\":[]}");
        assertThrows(IllegalStateException.class, () -> service.generate("theme", "mood", "style"));
    }

    @Test
    void generateThrowsOnMissingSections() {
        stubContent("{\"title\":\"T\"}");
        assertThrows(IllegalStateException.class, () -> service.generate("theme", "mood", "style"));
    }

    @Test
    void generateThrowsOnEmptyLyricsInSection() {
        stubContent("{\"title\":\"T\",\"sections\":[{\"name\":\"a\",\"lyrics\":\"\"}]}");
        assertThrows(IllegalStateException.class, () -> service.generate("theme", "mood", "style"));
    }

    @Test
    void generateClampsEstSecondsLowToFive() {
        stubContent("{\"title\":\"T\",\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\",\"estSeconds\":3}]}");
        LyricsResult result = service.generate("theme", "mood", "style");
        assertEquals(5, result.sections().get(0).estSeconds());
    }

    @Test
    void generateClampsEstSecondsHighToSixty() {
        stubContent("{\"title\":\"T\",\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\",\"estSeconds\":100}]}");
        LyricsResult result = service.generate("theme", "mood", "style");
        assertEquals(60, result.sections().get(0).estSeconds());
    }

    @Test
    void generateDefaultsEstSecondsWhenMissing() {
        stubContent("{\"title\":\"T\",\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\"}]}");
        LyricsResult result = service.generate("theme", "mood", "style");
        assertEquals(20, result.sections().get(0).estSeconds());
    }

    @Test
    void generateWithNullMoodDoesNotThrow() {
        stubContent("{\"title\":\"T\",\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\"}]}");
        LyricsResult result = service.generate("theme", null, "style");
        assertNotNull(result);
        assertEquals(1, result.sections().size());
    }

    @Test
    void toJsonContainsTitleAndSections() {
        stubContent("{\"title\":\"MyTitle\",\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\"}]}");
        LyricsResult result = service.generate("theme", "mood", "style");
        String json = service.toJson(result);
        assertTrue(json.contains("MyTitle"));
        assertTrue(json.contains("sections"));
    }
}
