package com.dramafactory.service;

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
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SkillServiceV220BTest {

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

    // ---------- publish ----------

    @Test
    void publish_nullAuthor_usesOfficialDefault() {
        when(skillRepository.findBySlug("my-skill")).thenReturn(Optional.empty());
        when(skillRepository.save(any(Skill.class))).thenAnswer(inv -> {
            Skill s = inv.getArgument(0);
            s.setId(10L);
            return s;
        });
        when(skillVersionRepository.save(any(SkillVersion.class))).thenAnswer(inv -> inv.getArgument(0));

        skillService.publish("名称", "my-skill", "描述", null, "SCRIPT",
                "a,b", "icon", "模板", "变更");

        ArgumentCaptor<Skill> captor = ArgumentCaptor.forClass(Skill.class);
        verify(skillRepository).save(captor.capture());
        assertEquals("官方", captor.getValue().getAuthor());
    }

    @Test
    void publish_blankAuthor_usesOfficialDefault() {
        when(skillRepository.findBySlug("my-skill")).thenReturn(Optional.empty());
        when(skillRepository.save(any(Skill.class))).thenAnswer(inv -> {
            Skill s = inv.getArgument(0);
            s.setId(10L);
            return s;
        });
        when(skillVersionRepository.save(any(SkillVersion.class))).thenAnswer(inv -> inv.getArgument(0));

        skillService.publish("名称", "my-skill", "描述", "   ", "SCRIPT",
                "a,b", "icon", "模板", "变更");

        ArgumentCaptor<Skill> captor = ArgumentCaptor.forClass(Skill.class);
        verify(skillRepository).save(captor.capture());
        assertEquals("官方", captor.getValue().getAuthor());
    }

    @Test
    void publish_nullChangelog_usesFirstReleaseDefault() {
        when(skillRepository.findBySlug("my-skill")).thenReturn(Optional.empty());
        when(skillRepository.save(any(Skill.class))).thenAnswer(inv -> {
            Skill s = inv.getArgument(0);
            s.setId(10L);
            return s;
        });
        when(skillVersionRepository.save(any(SkillVersion.class))).thenAnswer(inv -> inv.getArgument(0));

        skillService.publish("名称", "my-skill", "描述", "作者", "SCRIPT",
                "a,b", "icon", "模板", null);

        ArgumentCaptor<SkillVersion> captor = ArgumentCaptor.forClass(SkillVersion.class);
        verify(skillVersionRepository).save(captor.capture());
        assertEquals("首版发布", captor.getValue().getChangelog());
    }

    @Test
    void publish_blankChangelog_usesFirstReleaseDefault() {
        when(skillRepository.findBySlug("my-skill")).thenReturn(Optional.empty());
        when(skillRepository.save(any(Skill.class))).thenAnswer(inv -> {
            Skill s = inv.getArgument(0);
            s.setId(10L);
            return s;
        });
        when(skillVersionRepository.save(any(SkillVersion.class))).thenAnswer(inv -> inv.getArgument(0));

        skillService.publish("名称", "my-skill", "描述", "作者", "SCRIPT",
                "a,b", "icon", "模板", "   ");

        ArgumentCaptor<SkillVersion> captor = ArgumentCaptor.forClass(SkillVersion.class);
        verify(skillVersionRepository).save(captor.capture());
        assertEquals("首版发布", captor.getValue().getChangelog());
    }

    // ---------- publishVersion ----------

    @Test
    void publishVersion_nullVersion_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(1L, null, "模板", "变更"));
        assertEquals("version 格式不合法", ex.getMessage());
    }

    // ---------- list ----------

    @Test
    void list_blankQuery_skipsQueryFilter() {
        Skill s = new Skill();
        s.setId(1L);
        s.setName("Alpha");
        s.setSlug("alpha");
        s.setDescription("desc");
        s.setTags("a,b");
        s.setCategory("SCRIPT");
        s.setInstallCount(1L);
        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(s)));

        List<Skill> result = skillService.list("   ", null, null, null);

        assertEquals(1, result.size());
        assertEquals(1L, result.get(0).getId());
    }

    @Test
    void list_queryNoMatchOnAllFields_skipsSkill() {
        Skill s = new Skill();
        s.setId(1L);
        s.setName("Alpha");
        s.setSlug("alpha");
        s.setDescription("desc");
        s.setTags("a,b");
        s.setCategory("SCRIPT");
        s.setInstallCount(1L);
        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(s)));

        List<Skill> result = skillService.list("zzz", null, null, null);

        assertTrue(result.isEmpty());
    }

    @Test
    void list_tagNotNullButSkillTagsNull_skipsSkill() {
        Skill s = new Skill();
        s.setId(1L);
        s.setName("Alpha");
        s.setSlug("alpha");
        s.setDescription("desc");
        s.setTags(null);
        s.setCategory("SCRIPT");
        s.setInstallCount(1L);
        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(s)));

        List<Skill> result = skillService.list(null, "a", null, null);

        assertTrue(result.isEmpty());
    }

    @Test
    void list_tagMatchTrue_keepsSkill() {
        Skill s = new Skill();
        s.setId(1L);
        s.setName("Alpha");
        s.setSlug("alpha");
        s.setDescription("desc");
        s.setTags("a, b");
        s.setCategory("SCRIPT");
        s.setInstallCount(1L);
        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(s)));

        List<Skill> result = skillService.list(null, "b", null, null);

        assertEquals(1, result.size());
    }

    @Test
    void list_tagMatchFalse_skipsSkill() {
        Skill s = new Skill();
        s.setId(1L);
        s.setName("Alpha");
        s.setSlug("alpha");
        s.setDescription("desc");
        s.setTags("a,b");
        s.setCategory("SCRIPT");
        s.setInstallCount(1L);
        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(s)));

        List<Skill> result = skillService.list(null, "c", null, null);

        assertTrue(result.isEmpty());
    }

    @Test
    void list_sortRating_ordersByAvgRatingDescending() {
        Skill low = new Skill();
        low.setId(1L);
        low.setName("Low");
        low.setSlug("low");
        low.setCategory("SCRIPT");
        low.setInstallCount(1L);
        low.setRatingSum(2L);
        low.setRatingCount(1L);

        Skill high = new Skill();
        high.setId(2L);
        high.setName("High");
        high.setSlug("high");
        high.setCategory("SCRIPT");
        high.setInstallCount(1L);
        high.setRatingSum(10L);
        high.setRatingCount(2L);

        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(low, high)));

        List<Skill> result = skillService.list(null, null, null, "rating");

        assertEquals(2, result.size());
        assertEquals(2L, result.get(0).getId());
        assertEquals(1L, result.get(1).getId());
    }

    @Test
    void list_sortRating_nullAvgRatingGoesLast() {
        Skill rated = new Skill();
        rated.setId(1L);
        rated.setName("Rated");
        rated.setSlug("rated");
        rated.setCategory("SCRIPT");
        rated.setInstallCount(1L);
        rated.setRatingSum(6L);
        rated.setRatingCount(2L);

        Skill unrated = new Skill();
        unrated.setId(2L);
        unrated.setName("Unrated");
        unrated.setSlug("unrated");
        unrated.setCategory("SCRIPT");
        unrated.setInstallCount(1L);

        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(unrated, rated)));

        List<Skill> result = skillService.list(null, null, null, "rating");

        assertEquals(2, result.size());
        assertEquals(1L, result.get(0).getId());
        assertEquals(2L, result.get(1).getId());
    }

    @Test
    void list_blankSort_usesPopularDefault() {
        Skill low = new Skill();
        low.setId(1L);
        low.setName("Low");
        low.setSlug("low");
        low.setCategory("SCRIPT");
        low.setInstallCount(1L);

        Skill high = new Skill();
        high.setId(2L);
        high.setName("High");
        high.setSlug("high");
        high.setCategory("SCRIPT");
        high.setInstallCount(100L);

        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(low, high)));

        List<Skill> result = skillService.list(null, null, null, "   ");

        assertEquals(2, result.size());
        assertEquals(2L, result.get(0).getId());
    }

    @Test
    void list_invalidSort_throwsIllegalArgument() {
        Skill low = new Skill();
        low.setId(1L);
        low.setName("Low");
        low.setSlug("low");
        low.setCategory("SCRIPT");
        low.setInstallCount(1L);

        Skill high = new Skill();
        high.setId(2L);
        high.setName("High");
        high.setSlug("high");
        high.setCategory("SCRIPT");
        high.setInstallCount(100L);

        when(skillRepository.findAll()).thenReturn(new ArrayList<>(List.of(low, high)));

        assertThrows(IllegalArgumentException.class,
                () -> skillService.list(null, null, null, "unknown-sort"));
    }

    // ---------- install ----------

    @Test
    void install_blankVersion_usesLatestVersion() {
        Skill skill = new Skill();
        skill.setId(1L);
        skill.setName("Alpha");
        skill.setInstallCount(0L);

        SkillVersion latest = new SkillVersion();
        latest.setSkillId(1L);
        latest.setVersion("2.0.0");

        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L))
                .thenReturn(new ArrayList<>(List.of(latest)));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "2.0.0"))
                .thenReturn(Optional.of(latest));
        when(skillInstallRepository.findBySkillId(1L)).thenReturn(Optional.empty());
        when(skillInstallRepository.save(any(SkillInstall.class))).thenAnswer(inv -> inv.getArgument(0));
        when(skillRepository.save(any(Skill.class))).thenAnswer(inv -> inv.getArgument(0));

        SkillInstall result = skillService.install(1L, "   ");

        assertNotNull(result);
        assertEquals("2.0.0", result.getVersion());
    }

    // ---------- rate ----------

    @Test
    void rate_nullScore_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.rate(1L, null, "评论"));
        assertEquals("score 必须在 1~5 之间", ex.getMessage());
    }

    // ---------- renderTemplate ----------

    @Test
    void renderTemplate_nullVariables_missingVarKept() {
        Skill skill = new Skill();
        skill.setId(1L);

        SkillVersion version = new SkillVersion();
        version.setSkillId(1L);
        version.setVersion("1.0.0");
        version.setPromptTemplate("Hello {{name}}!");

        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.0"))
                .thenReturn(Optional.of(version));

        String rendered = skillService.renderTemplate(1L, "1.0.0", null);

        assertEquals("Hello {{name}}!", rendered);
    }
}
