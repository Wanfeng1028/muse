package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.*;

class ScriptServiceAiFallbackTest {

    private EpisodeRepository episodeRepository;
    private SceneRepository sceneRepository;
    private CharacterService characterService;

    private static class FailingLlmScriptService extends LlmScriptService {
        int callCount = 0;

        FailingLlmScriptService() {
            super(null, new ObjectMapper(), true, "test-model", 3000, 120, 0, null,
                    new com.dramafactory.metrics.DramaMetrics(
                            new io.micrometer.core.instrument.simple.SimpleMeterRegistry(), null, null));
        }

        @Override
        String callModel(ObjectNode body) {
            callCount++;
            throw new RuntimeException("ai down");
        }
    }

    @BeforeEach
    void setUp() {
        episodeRepository = mock(EpisodeRepository.class);
        sceneRepository = mock(SceneRepository.class);
        characterService = mock(CharacterService.class);
        when(characterService.listByProject(any())).thenReturn(List.of());
    }

    private Episode buildEpisode() {
        Episode episode = new Episode();
        episode.setId(1L);
        episode.setOutline("outline");
        DramaProject project = new DramaProject();
        project.setTitle("title");
        project.setGenre("genre");
        episode.setProject(project);
        return episode;
    }

    @Test
    void aiFailureFallsBackToTemplate() {
        Episode episode = buildEpisode();
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(episode));

        FailingLlmScriptService llm = new FailingLlmScriptService();
        ScriptService scriptService = new ScriptService(
                episodeRepository, sceneRepository, llm, characterService);

        Records.GenerateScriptResponse response = scriptService.generate(1L, "ai");

        assertEquals("template-fallback", response.source());
        assertEquals(4, response.sceneCount());
        assertEquals(EpisodeStatus.SCRIPTED, episode.getStatus());
        verify(episodeRepository, times(1)).save(episode);
    }

    @Test
    void templateModeDoesNotCallModel() {
        Episode episode = buildEpisode();
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(episode));

        FailingLlmScriptService llm = new FailingLlmScriptService();
        ScriptService scriptService = new ScriptService(
                episodeRepository, sceneRepository, llm, characterService);

        Records.GenerateScriptResponse response = scriptService.generate(1L, "template");

        assertEquals("template", response.source());
        assertEquals(0, llm.callCount);
    }

    @Test
    void invalidModeThrows() {
        Episode episode = buildEpisode();
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.of(episode));

        FailingLlmScriptService llm = new FailingLlmScriptService();
        ScriptService scriptService = new ScriptService(
                episodeRepository, sceneRepository, llm, characterService);

        assertThrows(IllegalArgumentException.class, () -> scriptService.generate(1L, "xx"));
    }

    @Test
    void missingEpisodeThrowsResourceNotFound() {
        when(episodeRepository.findById(anyLong())).thenReturn(Optional.empty());

        FailingLlmScriptService llm = new FailingLlmScriptService();
        ScriptService scriptService = new ScriptService(
                episodeRepository, sceneRepository, llm, characterService);

        assertThrows(ResourceNotFoundException.class, () -> scriptService.generate(99L, "ai"));
    }
}
