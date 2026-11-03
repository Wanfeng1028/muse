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
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SkillServiceV221ATest {

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

    // 1. L85 publish slug isBlank 臂
    @Test
    void publish_blankSlug_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("名字", "   ", "desc", "作者", "SCRIPT", "tag", "icon", "模板", "changelog"));
        assertEquals("slug 不能为空", ex.getMessage());
    }

    // 2. L139 publishVersion promptTemplate isBlank 臂
    @Test
    void publishVersion_blankPromptTemplate_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(1L, "1.0.1", "   ", "changelog"));
        assertEquals("promptTemplate 不能为空", ex.getMessage());
    }

    // 3. L171 matchName 中 skill.getName() != null 的 null 臂
    @Test
    void list_queryMatchesViaDescriptionWhenNameNull() {
        Skill skill = new Skill();
        skill.setName(null);
        skill.setDescription("abc desc");
        skill.setTags("abc-tag");
        skill.setSlug("abc-slug");
        when(skillRepository.findAll()).thenReturn(List.of(skill));

        List<Skill> result = skillService.list("abc", null, null, null);

        assertTrue(result.contains(skill));
    }

    // 4. L173 matchTags 中 skill.getTags() != null 的 null 臂
    @Test
    void list_queryMatchesWhenTagsNull() {
        Skill skill = new Skill();
        skill.setName("abc name");
        skill.setDescription(null);
        skill.setTags(null);
        skill.setSlug(null);
        when(skillRepository.findAll()).thenReturn(List.of(skill));

        List<Skill> result = skillService.list("abc", null, null, null);

        assertTrue(result.contains(skill));
    }

    // 5. L174 matchSlug 中 skill.getSlug() != null 的 null 臂
    @Test
    void list_queryMatchesWhenSlugNull() {
        Skill skill = new Skill();
        skill.setName("abc name");
        skill.setDescription(null);
        skill.setTags(null);
        skill.setSlug(null);
        when(skillRepository.findAll()).thenReturn(List.of(skill));

        List<Skill> result = skillService.list("abc", null, null, null);

        assertTrue(result.contains(skill));
    }

    // 6. L175 continue 臂：四字段都不匹配
    @Test
    void list_queryMatchesNothing_skillExcluded() {
        Skill skill = new Skill();
        skill.setName("xyz");
        skill.setDescription(null);
        skill.setTags(null);
        skill.setSlug(null);
        when(skillRepository.findAll()).thenReturn(List.of(skill));

        List<Skill> result = skillService.list("abc", null, null, null);

        assertFalse(result.contains(skill));
        assertTrue(result.isEmpty());
    }

    // 7. L179 tag isBlank 臂
    @Test
    void list_blankTag_skipsTagFilter() {
        Skill skill = new Skill();
        skill.setName("anything");
        skill.setCategory("SCRIPT");
        when(skillRepository.findAll()).thenReturn(List.of(skill));

        List<Skill> result = skillService.list(null, "   ", null, null);

        assertTrue(result.contains(skill));
    }

    // 8. L261 install 中 installCount == null 臂
    @Test
    void install_nullInstallCount_becomesOne() {
        Skill skill = new Skill();
        skill.setId(1L);
        skill.setInstallCount(null);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));

        SkillVersion version = new SkillVersion();
        version.setSkillId(1L);
        version.setVersion("1.0.0");
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.0")).thenReturn(Optional.of(version));

        SkillInstall install = new SkillInstall();
        install.setInstalledAt(LocalDateTime.now());
        when(skillInstallRepository.findBySkillId(1L)).thenReturn(Optional.of(install));
        when(skillInstallRepository.save(any(SkillInstall.class))).thenAnswer(inv -> inv.getArgument(0));
        when(skillRepository.save(any(Skill.class))).thenAnswer(inv -> inv.getArgument(0));

        skillService.install(1L, "1.0.0");

        assertEquals(1L, skill.getInstallCount());
    }

    // 9. L299 rate 中 ratingCount == null 臂
    @Test
    void rate_nullRatingCount_becomesOne() {
        Skill skill = new Skill();
        skill.setId(1L);
        skill.setRatingSum(0L);
        skill.setRatingCount(null);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));

        SkillRating saved = new SkillRating();
        saved.setSkillId(1L);
        saved.setScore(5);
        when(skillRatingRepository.save(any(SkillRating.class))).thenReturn(saved);
        when(skillRepository.save(any(Skill.class))).thenAnswer(inv -> inv.getArgument(0));

        skillService.rate(1L, 5, "good");

        assertEquals(1L, skill.getRatingCount());
        assertEquals(5L, skill.getRatingSum());
    }

    // 10. L318 renderTemplate 中 version 为 blank 走 latestVersion 臂
    @Test
    void renderTemplate_blankVersion_usesLatest() {
        Skill skill = new Skill();
        skill.setId(1L);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(skill));

        SkillVersion version = new SkillVersion();
        version.setSkillId(1L);
        version.setVersion("1.0.0");
        version.setPromptTemplate("你好 {{name}}");
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L)).thenReturn(List.of(version));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.0")).thenReturn(Optional.of(version));

        String rendered = skillService.renderTemplate(1L, "   ", Map.of("name", "世界"));

        assertEquals("你好 世界", rendered);
    }
}
