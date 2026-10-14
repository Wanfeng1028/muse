// SkillService.publish 分支覆盖（v2.14）
package com.dramafactory.service;

import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillVersion;
import com.dramafactory.repository.SkillInstallRepository;
import com.dramafactory.repository.SkillRatingRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.repository.SkillVersionRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SkillServicePublishBranchTest {

    @Mock
    SkillRepository skillRepository;

    @Mock
    SkillVersionRepository skillVersionRepository;

    @Mock
    SkillInstallRepository skillInstallRepository;

    @Mock
    SkillRatingRepository skillRatingRepository;

    @InjectMocks
    SkillService skillService;

    private void stubSave() {
        when(skillRepository.save(any(Skill.class))).thenAnswer(i -> {
            Skill s = i.getArgument(0);
            s.setId(9L);
            return s;
        });
    }

    @Test
    void publish_nullName_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish(null, "good-slug", "desc", "author",
                        "GENERAL", "tags", "ic", "template", "changelog"));
        assertTrue(ex.getMessage().contains("name"));
    }

    @Test
    void publish_nullSlug_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("name", null, "desc", "author",
                        "GENERAL", "tags", "ic", "template", "changelog"));
        assertTrue(ex.getMessage().contains("slug"));
    }

    @Test
    void publish_shortSlug_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("name", "ab", "desc", "author",
                        "GENERAL", "tags", "ic", "template", "changelog"));
        assertTrue(ex.getMessage().contains("格式不合法"));
    }

    @Test
    void publish_nullCategory_throws() {
        when(skillRepository.findBySlug("good-slug")).thenReturn(Optional.empty());

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("name", "good-slug", "desc", "author",
                        null, "tags", "ic", "template", "changelog"));
        assertTrue(ex.getMessage().contains("category"));
    }

    @Test
    void publish_nullTemplate_throws() {
        when(skillRepository.findBySlug("good-slug")).thenReturn(Optional.empty());

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("name", "good-slug", "desc", "author",
                        "GENERAL", "tags", "ic", null, "changelog"));
        assertTrue(ex.getMessage().contains("promptTemplate"));
    }

    @Test
    void publish_blankTemplate_throws() {
        when(skillRepository.findBySlug("good-slug")).thenReturn(Optional.empty());

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("name", "good-slug", "desc", "author",
                        "GENERAL", "tags", "ic", " ", "changelog"));
        assertTrue(ex.getMessage().contains("promptTemplate"));
    }

    @Test
    void publish_blankAuthor_savedAsOfficial() {
        when(skillRepository.findBySlug("good-slug")).thenReturn(Optional.empty());
        stubSave();

        skillService.publish("name", "good-slug", "desc", "",
                "GENERAL", "tags", "ic", "template", "changelog");

        ArgumentCaptor<Skill> captor = ArgumentCaptor.forClass(Skill.class);
        org.mockito.Mockito.verify(skillRepository).save(captor.capture());
        assertEquals("官方", captor.getValue().getAuthor());
    }

    @Test
    void publish_nullChangelog_defaultsToFirstRelease() {
        when(skillRepository.findBySlug("good-slug")).thenReturn(Optional.empty());
        stubSave();

        skillService.publish("name", "good-slug", "desc", "author",
                "GENERAL", "tags", "ic", "template", null);

        ArgumentCaptor<SkillVersion> captor = ArgumentCaptor.forClass(SkillVersion.class);
        org.mockito.Mockito.verify(skillVersionRepository).save(captor.capture());
        assertEquals("首版发布", captor.getValue().getChangelog());
        assertEquals("1.0.0", captor.getValue().getVersion());
    }

    @Test
    void publish_fieldsPassthrough() {
        when(skillRepository.findBySlug("good-slug")).thenReturn(Optional.empty());
        stubSave();

        skillService.publish("name", "good-slug", "desc", "author",
                "GENERAL", "tags", "ic", "template", "changelog");

        ArgumentCaptor<Skill> captor = ArgumentCaptor.forClass(Skill.class);
        org.mockito.Mockito.verify(skillRepository).save(captor.capture());
        Skill saved = captor.getValue();
        assertEquals("desc", saved.getDescription());
        assertEquals("ic", saved.getIcon());
        assertEquals(Boolean.FALSE, saved.getOfficial());
    }
}
