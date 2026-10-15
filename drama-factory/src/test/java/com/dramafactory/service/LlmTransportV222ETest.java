package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.*;

class LlmTransportV222ETest {

    @Test
    void parseProxyReturnsEmptyWhenHostNull() {
        assertTrue(LlmTransport.parseProxy("file:///tmp/x").isEmpty());
    }

    @Test
    void parseProxyReturnsSpecWhenUserInfoNull() {
        Optional<LlmTransport.ProxySpec> result = LlmTransport.parseProxy("http://proxy.example.com:8080");
        assertTrue(result.isPresent());
        LlmTransport.ProxySpec spec = result.get();
        assertEquals("proxy.example.com", spec.host());
        assertEquals(8080, spec.port());
        assertNull(spec.user());
        assertNull(spec.pass());
    }

    @Test
    void resolveProxyReturnsEmptyWhenEnvNull() {
        assertTrue(LlmTransport.resolveProxy(null).isEmpty());
    }

    @Test
    void generateUsesSourceWhenDescriptionBlank() {
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        SceneRepository sceneRepository = mock(SceneRepository.class);
        LlmScriptService llm = mock(LlmScriptService.class);
        CharacterService characterService = mock(CharacterService.class);
        SkillService skillService = mock(SkillService.class);

        when(llm.generate(any(), any(), any()))
                .thenReturn(new LlmScriptService.LlmScriptResult(List.of(), "m", 1L, 0L, 0L));

        Episode e = new Episode();
        e.setId(1L);
        DramaProject p = new DramaProject();
        p.setId(9L);
        e.setProject(p);
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(e));

        when(characterService.listByProject(any()))
                .thenReturn(List.of(new Records.CharacterResponse(1L, 9L, "甲", null, "   ", null, null, null)));

        ScriptService service = new ScriptService(episodeRepository, sceneRepository, llm, characterService, skillService);

        assertEquals("ai", service.generate(1L, "ai").source());
    }
}
