package com.dramafactory.service;

import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillInstall;
import com.dramafactory.model.SkillRating;
import com.dramafactory.model.SkillVersion;
import com.dramafactory.exception.ResourceNotFoundException;
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
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class SkillServiceTest {

    @Mock private SkillRepository skillRepository;
    @Mock private SkillVersionRepository skillVersionRepository;
    @Mock private SkillInstallRepository skillInstallRepository;
    @Mock private SkillRatingRepository skillRatingRepository;

    @InjectMocks private SkillService skillService;

    private Skill skill(long id, String name, String slug, String category, String tags,
                        long installCount, long ratingSum, long ratingCount) {
        Skill s = new Skill();
        s.setId(id);
        s.setName(name);
        s.setSlug(slug);
        s.setCategory(category);
        s.setTags(tags);
        s.setInstallCount(installCount);
        s.setRatingSum(ratingSum);
        s.setRatingCount(ratingCount);
        return s;
    }

    // 1
    @Test
    void publish_blankName_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("", "good-slug", "d", "a", "SCRIPT",
                        "t", "i", "pt", "c"));
        assertTrue(ex.getMessage().toLowerCase().contains("name"));
    }

    // 2
    @Test
    void publish_badSlug_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("n", "AB C", "d", "a", "SCRIPT",
                        "t", "i", "pt", "c"));
        assertNotNull(ex.getMessage());
    }

    // 3
    @Test
    void publish_duplicateSlug_throws() {
        when(skillRepository.findBySlug("dup-slug"))
                .thenReturn(Optional.of(skill(1L, "x", "dup-slug", "SCRIPT", null, 0, 0, 0)));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("n", "dup-slug", "d", "a", "SCRIPT",
                        "t", "i", "pt", "c"));
        assertNotNull(ex.getMessage());
    }

    // 4
    @Test
    void publish_badCategory_throws() {
        when(skillRepository.findBySlug("uniq-slug")).thenReturn(Optional.empty());
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("n", "uniq-slug", "d", "a", "UNKNOWN",
                        "t", "i", "pt", "c"));
        assertNotNull(ex.getMessage());
    }

    // 5
    @Test
    void publish_happy_createsSkillAndV100() {
        when(skillRepository.findBySlug("new-slug")).thenReturn(Optional.empty());
        when(skillRepository.save(any(Skill.class))).thenAnswer(i -> {
            Skill s = i.getArgument(0);
            s.setId(9L);
            return s;
        });

        Skill result = skillService.publish("我的技能", "new-slug", "desc", "author",
                "SCRIPT", "a,b", "icon", "prompt {{x}}", "changelog");

        assertEquals("我的技能", result.getName());
        assertEquals(9L, result.getId());

        ArgumentCaptor<SkillVersion> captor = ArgumentCaptor.forClass(SkillVersion.class);
        verify(skillVersionRepository).save(captor.capture());
        SkillVersion saved = captor.getValue();
        assertEquals("1.0.0", saved.getVersion());
        assertEquals(9L, saved.getSkillId());
        assertEquals("prompt {{x}}", saved.getPromptTemplate());
    }

    // 6
    @Test
    void publishVersion_badFormat_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(1L, "1.0", "pt", "c"));
        assertNotNull(ex.getMessage());
    }

    // 7
    @Test
    void publishVersion_duplicate_throws() {
        Skill s = skill(1L, "n", "s", "SCRIPT", null, 0L, 0L, 0L);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.1"))
                .thenReturn(Optional.of(new SkillVersion()));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(1L, "1.0.1", "pt", "c"));
        assertNotNull(ex.getMessage());
    }

    // 8
    @Test
    void list_filtersAndSorts() {
        Skill a = skill(1L, "Alpha", "alpha", "SCRIPT", "hook,start", 10, 40, 10); // 4.0
        Skill b = skill(2L, "Beta", "beta", "BOARD", "hook", 5, 20, 5);            // 4.0
        Skill c = skill(3L, "Gamma", "gamma", "SCRIPT", "other", 99, 30, 10);      // 3.0
        when(skillRepository.findAll()).thenReturn(List.of(a, b, c));

        List<Skill> all = skillService.list(null, null, null, null);
        assertEquals(3, all.size());

        List<Skill> byQuery = skillService.list("al", null, null, null);
        assertEquals(1, byQuery.size());
        assertEquals("Alpha", byQuery.get(0).getName());

        List<Skill> byTag = skillService.list(null, "hook", null, null);
        assertEquals(2, byTag.size());

        List<Skill> byCategory = skillService.list(null, null, "SCRIPT", null);
        assertEquals(2, byCategory.size());

        List<Skill> popular = skillService.list(null, null, null, "popular");
        assertEquals(3, popular.size());
        assertEquals(99, popular.get(0).getInstallCount());
        assertEquals(10, popular.get(1).getInstallCount());
        assertEquals(5, popular.get(2).getInstallCount());
    }

    // 9
    @Test
    void install_usesLatestWhenVersionNull() {
        Skill s = skill(1L, "n", "slug", "SCRIPT", null, 5, 0, 0);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s));

        SkillVersion v101 = new SkillVersion();
        v101.setSkillId(1L);
        v101.setVersion("1.0.1");
        SkillVersion v100 = new SkillVersion();
        v100.setSkillId(1L);
        v100.setVersion("1.0.0");
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L))
                .thenReturn(List.of(v101, v100));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.1"))
                .thenReturn(Optional.of(v101));

        when(skillInstallRepository.findBySkillId(1L)).thenReturn(Optional.empty());
        when(skillInstallRepository.save(any(SkillInstall.class)))
                .thenAnswer(i -> i.getArgument(0));

        SkillInstall install = skillService.install(1L, null);

        assertEquals("1.0.1", install.getVersion());

        ArgumentCaptor<Skill> skillCaptor = ArgumentCaptor.forClass(Skill.class);
        verify(skillRepository).save(skillCaptor.capture());
        assertEquals(6, skillCaptor.getValue().getInstallCount());
    }

    // 10
    @Test
    void install_unknownVersion_throws() {
        when(skillRepository.findById(1L))
                .thenReturn(Optional.of(skill(1L, "n", "slug", "SCRIPT", null, 0, 0, 0)));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "9.9.9"))
                .thenReturn(Optional.empty());
        assertThrows(IllegalArgumentException.class, () -> skillService.install(1L, "9.9.9"));
    }

    // 11
    @Test
    void uninstall_notInstalled_throws() {
        when(skillInstallRepository.findBySkillId(1L)).thenReturn(Optional.empty());
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> skillService.uninstall(1L));
        assertNotNull(ex);
    }

    // 12
    @Test
    void rate_scoreOutOfRange_throws() {
        assertThrows(IllegalArgumentException.class, () -> skillService.rate(1L, 6, "c"));
        assertThrows(IllegalArgumentException.class, () -> skillService.rate(1L, 0, "c"));
    }

    // 13
    @Test
    void rate_happy_updatesSumAndCount() {
        Skill s = skill(1L, "n", "slug", "SCRIPT", null, 0, 8, 2);
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s));
        when(skillRatingRepository.save(any(SkillRating.class)))
                .thenAnswer(i -> i.getArgument(0));

        SkillRating rating = skillService.rate(1L, 5, "好");

        assertEquals(5, rating.getScore());

        ArgumentCaptor<Skill> captor = ArgumentCaptor.forClass(Skill.class);
        verify(skillRepository).save(captor.capture());
        assertEquals(13, captor.getValue().getRatingSum());
        assertEquals(3, captor.getValue().getRatingCount());
    }

    // 14
    @Test
    void renderTemplate_lenient_keepsMissingVar() {
        SkillVersion v = new SkillVersion();
        v.setSkillId(1L);
        v.setVersion("1.0.0");
        v.setPromptTemplate("A{{x}}B{{y}}");
        when(skillRepository.findById(1L))
                .thenReturn(Optional.of(skill(1L, "n", "slug", "SCRIPT", null, 0, 0, 0)));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.0"))
                .thenReturn(Optional.of(v));

        String out = skillService.renderTemplate(1L, "1.0.0", Map.of("x", "1"));
        assertEquals("A1B{{y}}", out);
    }

    // 15
    @Test
    void resolveForUse_notInstalled_throws() {
        when(skillRepository.findById(1L))
                .thenReturn(Optional.of(skill(1L, "n", "slug", "SCRIPT", null, 0, 0, 0)));
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L))
                .thenReturn(List.of());
        when(skillInstallRepository.findBySkillId(1L)).thenReturn(Optional.empty());

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.resolveForUse(1L, Map.of()));
        assertTrue(ex.getMessage().contains("安装"));
    }
}
