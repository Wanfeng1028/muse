package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.InjectMocks;
import org.mockito.ArgumentCaptor;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

import com.dramafactory.model.AgentType;
import com.dramafactory.model.PromptTemplate;
import com.dramafactory.repository.PromptTemplateRepository;
import com.dramafactory.service.PromptTemplateService;

import java.util.List;
import java.util.Set;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.Arrays;

@ExtendWith(MockitoExtension.class)
class PromptTemplateServiceBackfillTest {

    @Mock
    private PromptTemplateRepository repository;

    @InjectMocks
    private PromptTemplateService service;

    @Test
    @DisplayName("oldDbBackfill")
    void oldDbBackfill() {
        // Existing templates for SCRIPT, BOARD, VIDEO, EDIT, QC
        PromptTemplate scriptTemplate = new PromptTemplate();
        scriptTemplate.setAgentType(AgentType.SCRIPT);
        scriptTemplate.setContent("用户改过的内容");
        when(repository.findByAgentType(AgentType.SCRIPT)).thenReturn(Optional.of(scriptTemplate));

        PromptTemplate boardTemplate = new PromptTemplate();
        boardTemplate.setAgentType(AgentType.BOARD);
        when(repository.findByAgentType(AgentType.BOARD)).thenReturn(Optional.of(boardTemplate));

        PromptTemplate videoTemplate = new PromptTemplate();
        videoTemplate.setAgentType(AgentType.VIDEO);
        when(repository.findByAgentType(AgentType.VIDEO)).thenReturn(Optional.of(videoTemplate));

        PromptTemplate editTemplate = new PromptTemplate();
        editTemplate.setAgentType(AgentType.EDIT);
        when(repository.findByAgentType(AgentType.EDIT)).thenReturn(Optional.of(editTemplate));

        PromptTemplate qcTemplate = new PromptTemplate();
        qcTemplate.setAgentType(AgentType.QC);
        when(repository.findByAgentType(AgentType.QC)).thenReturn(Optional.of(qcTemplate));

        // Missing templates for LYRICS and COMPOSE
        when(repository.findByAgentType(AgentType.LYRICS)).thenReturn(Optional.empty());
        when(repository.findByAgentType(AgentType.COMPOSE)).thenReturn(Optional.empty());

        // Execute back‑fill
        service.run(null);

        // Verify save called exactly twice
        ArgumentCaptor<PromptTemplate> saveCaptor = ArgumentCaptor.forClass(PromptTemplate.class);
        verify(repository, times(2)).save(saveCaptor.capture());
        List<PromptTemplate> saved = saveCaptor.getAllValues();

        assertThat(saved).hasSize(2);
        Set<AgentType> savedAgentTypes = saved.stream()
                .map(PromptTemplate::getAgentType)
                .collect(Collectors.toSet());
        assertThat(savedAgentTypes).containsExactlyInAnyOrder(AgentType.LYRICS, AgentType.COMPOSE);

        // Verify names and non‑empty content for the two new templates
        for (PromptTemplate pt : saved) {
            if (pt.getAgentType() == AgentType.LYRICS) {
                assertThat(pt.getName()).isEqualTo("作词默认模板");
            } else if (pt.getAgentType() == AgentType.COMPOSE) {
                assertThat(pt.getName()).isEqualTo("作曲默认模板");
            }
            assertThat(pt.getContent()).isNotNull().isNotEmpty();
            assertThat(pt.getUpdatedAt()).isNotNull();
        }

        // Ensure the existing SCRIPT template was not saved and its content unchanged
        assertThat(scriptTemplate.getContent()).isEqualTo("用户改过的内容");
    }

    @Test
    @DisplayName("freshDb")
    void freshDb() {
        // No existing templates for any agent type
        for (AgentType at : AgentType.values()) {
            when(repository.findByAgentType(at)).thenReturn(Optional.empty());
        }

        service.run(null);

        // Should have saved 7 new templates
        ArgumentCaptor<PromptTemplate> saveCaptor = ArgumentCaptor.forClass(PromptTemplate.class);
        verify(repository, times(7)).save(saveCaptor.capture());
        List<PromptTemplate> saved = saveCaptor.getAllValues();
        assertThat(saved).hasSize(7);

        Set<AgentType> savedAgentTypes = saved.stream()
                .map(PromptTemplate::getAgentType)
                .collect(Collectors.toSet());
        assertThat(savedAgentTypes).hasSize(7);
        assertThat(savedAgentTypes).containsExactlyInAnyOrderElementsOf(Arrays.asList(AgentType.values()));

        for (PromptTemplate pt : saved) {
            assertThat(pt.getContent()).isNotNull().isNotEmpty();
            assertThat(pt.getName()).isNotNull().isNotEmpty();
            assertThat(pt.getUpdatedAt()).isNotNull();
        }
    }

    @Test
    @DisplayName("completeDb")
    void completeDb() {
        // All agent types already have a template
        for (AgentType at : AgentType.values()) {
            PromptTemplate tmpl = new PromptTemplate();
            tmpl.setAgentType(at);
            tmpl.setContent("existing");
            when(repository.findByAgentType(at)).thenReturn(Optional.of(tmpl));
        }

        service.run(null);

        // No new saves should be performed
        verify(repository, never()).save(any());
    }

    @Test
    @DisplayName("findByAgentTypeCalledForAll")
    void findByAgentTypeCalledForAll() {
        // Setup same state as oldDbBackfill (some exist, some missing)
        PromptTemplate scriptTemplate = new PromptTemplate();
        scriptTemplate.setAgentType(AgentType.SCRIPT);
        scriptTemplate.setContent("用户改过的内容");
        when(repository.findByAgentType(AgentType.SCRIPT)).thenReturn(Optional.of(scriptTemplate));

        PromptTemplate boardTemplate = new PromptTemplate();
        boardTemplate.setAgentType(AgentType.BOARD);
        when(repository.findByAgentType(AgentType.BOARD)).thenReturn(Optional.of(boardTemplate));

        PromptTemplate videoTemplate = new PromptTemplate();
        videoTemplate.setAgentType(AgentType.VIDEO);
        when(repository.findByAgentType(AgentType.VIDEO)).thenReturn(Optional.of(videoTemplate));

        PromptTemplate editTemplate = new PromptTemplate();
        editTemplate.setAgentType(AgentType.EDIT);
        when(repository.findByAgentType(AgentType.EDIT)).thenReturn(Optional.of(editTemplate));

        PromptTemplate qcTemplate = new PromptTemplate();
        qcTemplate.setAgentType(AgentType.QC);
        when(repository.findByAgentType(AgentType.QC)).thenReturn(Optional.of(qcTemplate));

        when(repository.findByAgentType(AgentType.LYRICS)).thenReturn(Optional.empty());
        when(repository.findByAgentType(AgentType.COMPOSE)).thenReturn(Optional.empty());

        service.run(null);

        // Verify findByAgentType was called exactly once for each AgentType
        for (AgentType at : AgentType.values()) {
            verify(repository, times(1)).findByAgentType(at);
        }

        // Additionally ensure the expected two inserts happened
        ArgumentCaptor<PromptTemplate> saveCaptor = ArgumentCaptor.forClass(PromptTemplate.class);
        verify(repository, times(2)).save(saveCaptor.capture());
        List<PromptTemplate> saved = saveCaptor.getAllValues();
        Set<AgentType> savedTypes = saved.stream()
                .map(PromptTemplate::getAgentType)
                .collect(Collectors.toSet());
        assertThat(savedTypes).containsExactlyInAnyOrder(AgentType.LYRICS, AgentType.COMPOSE);
    }
}
