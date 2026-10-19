package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.Episode;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class SkillScriptGenerateTest {

    @Mock private EpisodeRepository episodeRepository;
    @Mock private SceneRepository sceneRepository;
    @Mock private LlmScriptService llmScriptService;
    @Mock private CharacterService characterService;
    @Mock private SkillService skillService;

    private ScriptService scriptService;

    @BeforeEach
    void setUp() {
        scriptService = new ScriptService(episodeRepository, sceneRepository,
                llmScriptService, characterService, skillService, mock(ReviewService.class));
    }

    private Episode episode() {
        Episode e = mock(Episode.class);
        when(e.getTitle()).thenReturn("测试剧");
        when(e.getOutline()).thenReturn("大纲");
        return e;
    }

    @Test
    void generate_withSkill_passesRenderedPromptToLlm() {
        Episode e = episode();
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(e));

        when(skillService.resolveForUse(eq(7L), anyMap()))
                .thenReturn(new SkillService.ResolvedSkill(7L, "短剧钩子开头", "1.0.0", "钩子模板正文"));

        when(llmScriptService.generate(eq(e), anyString(), any()))
                .thenReturn(new LlmScriptService.LlmScriptResult(
                        List.of(new ScriptGenerator.SceneDraft(1, "客厅", "白天", "画面", "对白", "prompt")),
                        "Deepseek-v4-flash", 10L, 5L, 6L));

        Records.GenerateScriptResponse response = scriptService.generate(1L, "ai", 7L);

        ArgumentCaptor<String> skillPromptCaptor = ArgumentCaptor.forClass(String.class);
        verify(llmScriptService).generate(eq(e), anyString(), skillPromptCaptor.capture());
        assertEquals("钩子模板正文", skillPromptCaptor.getValue());

        assertEquals("短剧钩子开头 v1.0.0", response.usedSkill());
        assertEquals("ai", response.source());
    }

    @Test
    void generate_withoutSkill_passesNullPromptAndNullUsedSkill() {
        Episode e = mock(Episode.class);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(e));

        when(llmScriptService.generate(eq(e), anyString(), any()))
                .thenReturn(new LlmScriptService.LlmScriptResult(
                        List.of(new ScriptGenerator.SceneDraft(1, "客厅", "白天", "画面", "对白", "prompt")),
                        "Deepseek-v4-flash", 10L, 5L, 6L));

        Records.GenerateScriptResponse response = scriptService.generate(1L, "ai", null);

        ArgumentCaptor<String> skillPromptCaptor = ArgumentCaptor.forClass(String.class);
        verify(llmScriptService).generate(eq(e), anyString(), skillPromptCaptor.capture());
        assertNull(skillPromptCaptor.getValue());

        assertNull(response.usedSkill());
    }
}
