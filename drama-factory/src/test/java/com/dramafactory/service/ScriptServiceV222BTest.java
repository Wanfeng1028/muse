package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.CharacterRole;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

/**
 * 补覆盖测试，目标类 {@link ScriptService}，覆盖 jacoco missed-branch 清单：
 * L104、L105、L185、L189、L194、L196、L201。
 */
@ExtendWith(MockitoExtension.class)
class ScriptServiceV222BTest {

    @Mock
    private EpisodeRepository episodeRepository;

    @Mock
    private SceneRepository sceneRepository;

    @Mock
    private LlmScriptService llmScriptService;

    @Mock
    private CharacterService characterService;

    @Mock
    private SkillService skillService;

    private ScriptService newService() {
        return new ScriptService(episodeRepository, sceneRepository, llmScriptService, characterService, skillService);
    }

    private void stubAiEmpty() {
        when(llmScriptService.generate(any(), any(), any()))
                .thenReturn(new LlmScriptService.LlmScriptResult(List.of(), "test-model", 1L, 0L, 0L));
    }

    private void stubSkill() {
        when(skillService.resolveForUse(eq(7L), any()))
                .thenReturn(new SkillService.ResolvedSkill(7L, "悬疑钩子", "1.0", "prompt"));
    }

    private Records.CharacterResponse character(Long id, String name, String description) {
        return new Records.CharacterResponse(id, 1L, name, null, description, null, null, null);
    }

    @Test
    void generateWithSkillTitleNullUsesEmptyString() {
        ScriptService service = newService();
        Episode e = new Episode();
        e.setId(1L);
        e.setTitle(null);
        e.setOutline("大纲内容");
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(e));
        stubSkill();

        service.generate(1L, "template", 7L);

        ArgumentCaptor<Map<String, String>> captor = ArgumentCaptor.forClass(Map.class);
        org.mockito.Mockito.verify(skillService).resolveForUse(eq(7L), captor.capture());
        assertEquals("", captor.getValue().get("剧集标题"));
        assertEquals("大纲内容", captor.getValue().get("大纲"));
    }

    @Test
    void generateWithSkillOutlineNullUsesEmptyString() {
        ScriptService service = newService();
        Episode e = new Episode();
        e.setId(1L);
        e.setTitle("标题内容");
        e.setOutline(null);
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(e));
        stubSkill();

        service.generate(1L, "template", 7L);

        ArgumentCaptor<Map<String, String>> captor = ArgumentCaptor.forClass(Map.class);
        org.mockito.Mockito.verify(skillService).resolveForUse(eq(7L), captor.capture());
        assertEquals("标题内容", captor.getValue().get("剧集标题"));
        assertEquals("", captor.getValue().get("大纲"));
    }

    @Test
    void aiModeProjectIdNullReturnsEmptySummary() {
        ScriptService service = newService();
        Episode e = new Episode();
        e.setId(1L);
        DramaProject p = new DramaProject();
        e.setProject(p);
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(e));
        stubAiEmpty();

        Records.GenerateScriptResponse resp = service.generate(1L, "ai");

        assertNotNull(resp);
        assertEquals("ai", resp.source());
    }

    @Test
    void aiModeCharactersNullStillSucceeds() {
        ScriptService service = newService();
        Episode e = new Episode();
        e.setId(1L);
        DramaProject p = new DramaProject();
        p.setId(10L);
        e.setProject(p);
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(e));
        when(characterService.listByProject(any())).thenReturn(null);
        stubAiEmpty();

        Records.GenerateScriptResponse resp = service.generate(1L, "ai");

        assertNotNull(resp);
        assertEquals("ai", resp.source());
    }

    @Test
    void aiModeCharactersEmptyStillSucceeds() {
        ScriptService service = newService();
        Episode e = new Episode();
        e.setId(1L);
        DramaProject p = new DramaProject();
        p.setId(10L);
        e.setProject(p);
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(e));
        when(characterService.listByProject(any())).thenReturn(List.of());
        stubAiEmpty();

        Records.GenerateScriptResponse resp = service.generate(1L, "ai");

        assertNotNull(resp);
        assertEquals("ai", resp.source());
    }

    @Test
    void aiModeCharactersTwoEntriesCoversLoopSeparatorAndDescriptionBranches() {
        ScriptService service = newService();
        Episode e = new Episode();
        e.setId(1L);
        DramaProject p = new DramaProject();
        p.setId(10L);
        e.setProject(p);
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(e));
        when(characterService.listByProject(any()))
                .thenReturn(List.of(
                        character(1L, "甲", "冷酷杀手"),
                        character(2L, "乙", null)));
        stubAiEmpty();

        Records.GenerateScriptResponse resp = service.generate(1L, "ai");

        assertNotNull(resp);
        assertEquals("ai", resp.source());
    }
}
