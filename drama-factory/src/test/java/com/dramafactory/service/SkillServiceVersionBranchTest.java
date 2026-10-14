// SkillService publishVersion/install/rate 分支覆盖（v2.14）
package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillInstall;
import com.dramafactory.model.SkillRating;
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

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SkillServiceVersionBranchTest {

    @Mock
    private SkillRepository skillRepository;

    @Mock
    private SkillVersionRepository skillVersionRepository;

    @Mock
    private SkillInstallRepository skillInstallRepository;

    @Mock
    private SkillRatingRepository skillRatingRepository;

    @InjectMocks
    private SkillService skillService;

    private Skill newSkill(Long id) {
        Skill skill = new Skill();
        skill.setId(id);
        skill.setInstallCount(0L);
        skill.setRatingSum(0L);
        skill.setRatingCount(0L);
        return skill;
    }

    private SkillVersion newVersion(Long skillId, String version) {
        SkillVersion v = new SkillVersion();
        v.setSkillId(skillId);
        v.setVersion(version);
        return v;
    }

    // 1
    @Test
    void publishVersion_nullVersion_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(1L, null, "prompt", "changelog"));
        assertTrue(ex.getMessage().contains("version"), "消息应包含 version，实际: " + ex.getMessage());
    }

    // 2
    @Test
    void publishVersion_blankTemplate_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(1L, "1.0.1", " ", "changelog"));
        assertTrue(ex.getMessage().contains("promptTemplate"), "消息应包含 promptTemplate，实际: " + ex.getMessage());
    }

    // 3
    @Test
    void publishVersion_skillNotFound_throws() {
        when(skillRepository.findById(1L)).thenReturn(Optional.empty());

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> skillService.publishVersion(1L, "1.0.1", "prompt", "changelog"));
        assertTrue(ex.getMessage().contains("Skill"), "消息应包含 Skill，实际: " + ex.getMessage());
    }

    // 4
    @Test
    void publishVersion_happy() {
        Skill skill = newSkill(1L);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.1")).thenReturn(Optional.empty());
        when(skillVersionRepository.save(any(SkillVersion.class))).thenAnswer(i -> i.getArgument(0));

        SkillVersion result = skillService.publishVersion(1L, "1.0.1", "prompt-tpl", "fix");

        assertEquals("1.0.1", result.getVersion());

        ArgumentCaptor<SkillVersion> captor = ArgumentCaptor.forClass(SkillVersion.class);
        org.mockito.Mockito.verify(skillVersionRepository).save(captor.capture());
        SkillVersion captured = captor.getValue();
        assertEquals(1L, captured.getSkillId());
        assertEquals("prompt-tpl", captured.getPromptTemplate());
    }

    // 5
    @Test
    void install_blankVersion_usesLatest() {
        Skill skill = newSkill(1L);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));

        SkillVersion v101 = newVersion(1L, "1.0.1");
        SkillVersion v100 = newVersion(1L, "1.0.0");
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L)).thenReturn(List.of(v101, v100));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.1")).thenReturn(Optional.of(v101));
        when(skillInstallRepository.findBySkillId(1L)).thenReturn(Optional.empty());
        when(skillInstallRepository.save(any(SkillInstall.class))).thenAnswer(i -> i.getArgument(0));
        when(skillRepository.save(any(Skill.class))).thenAnswer(i -> i.getArgument(0));

        SkillInstall result = skillService.install(1L, "");

        assertEquals("1.0.1", result.getVersion());
    }

    // 6
    @Test
    void install_noVersion_throws() {
        Skill skill = newSkill(1L);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L)).thenReturn(List.of());

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.install(1L, ""));
        assertTrue(ex.getMessage().contains("尚无版本"), "消息应包含 尚无版本，实际: " + ex.getMessage());
    }

    // 7
    @Test
    void install_existingInstall_keepsInstalledAt() {
        Skill skill = newSkill(1L);
        skill.setInstallCount(5L);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));

        SkillVersion v100 = newVersion(1L, "1.0.0");
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.0")).thenReturn(Optional.of(v100));

        LocalDateTime original = LocalDateTime.of(2026, 1, 1, 0, 0);
        SkillInstall existing = new SkillInstall();
        existing.setSkillId(1L);
        existing.setVersion("1.0.0");
        existing.setInstalledAt(original);
        when(skillInstallRepository.findBySkillId(1L)).thenReturn(Optional.of(existing));
        when(skillInstallRepository.save(any(SkillInstall.class))).thenAnswer(i -> i.getArgument(0));
        when(skillRepository.save(any(Skill.class))).thenAnswer(i -> i.getArgument(0));

        SkillInstall result = skillService.install(1L, "1.0.0");

        ArgumentCaptor<SkillInstall> installCaptor = ArgumentCaptor.forClass(SkillInstall.class);
        org.mockito.Mockito.verify(skillInstallRepository).save(installCaptor.capture());
        assertNotNull(installCaptor.getValue().getInstalledAt());
        assertEquals(original, installCaptor.getValue().getInstalledAt());

        ArgumentCaptor<Skill> skillCaptor = ArgumentCaptor.forClass(Skill.class);
        org.mockito.Mockito.verify(skillRepository).save(skillCaptor.capture());
        assertEquals(6L, skillCaptor.getValue().getInstallCount());

        assertEquals("1.0.0", result.getVersion());
    }

    // 8
    @Test
    void rate_nullScore_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.rate(1L, null, "comment"));
        assertTrue(ex.getMessage().contains("score"), "消息应包含 score，实际: " + ex.getMessage());
    }

    // 9
    @Test
    void rate_skillNotFound_throws() {
        when(skillRepository.findById(1L)).thenReturn(Optional.empty());

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> skillService.rate(1L, 4, "comment"));
        assertTrue(ex.getMessage().contains("Skill"), "消息应包含 Skill，实际: " + ex.getMessage());
    }

    // 10
    @Test
    void rate_nullSum_accumulatesFromZero() {
        Skill skill = newSkill(1L);
        skill.setRatingSum(null);
        skill.setRatingCount(2L);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));
        when(skillRatingRepository.save(any(SkillRating.class))).thenAnswer(i -> i.getArgument(0));
        when(skillRepository.save(any(Skill.class))).thenAnswer(i -> i.getArgument(0));

        skillService.rate(1L, 4, null);

        ArgumentCaptor<Skill> skillCaptor = ArgumentCaptor.forClass(Skill.class);
        org.mockito.Mockito.verify(skillRepository).save(skillCaptor.capture());
        assertEquals(4L, skillCaptor.getValue().getRatingSum());
        assertEquals(3L, skillCaptor.getValue().getRatingCount());
    }
}
