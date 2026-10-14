// SkillService.list 分支覆盖（v2.14）。
package com.dramafactory.service;

import com.dramafactory.model.Skill;
import com.dramafactory.repository.SkillRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SkillServiceListBranchTest {

    @Mock
    private SkillRepository skillRepository;

    @InjectMocks
    private SkillService skillService;

    private Skill mk(long id, String name, String slug, String category, String tags) {
        Skill s = new Skill();
        s.setId(id);
        s.setName(name);
        s.setSlug(slug);
        s.setCategory(category);
        s.setTags(tags);
        return s;
    }

    @Test
    void list_blankQuery_noFiltering() {
        Skill a = mk(1L, "Alpha", "alpha", "tool", "hook");
        Skill b = mk(2L, "Beta", "beta", "tool", "hook");
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list(" ", null, null, null);

        assertEquals(2, result.size());
    }

    @Test
    void list_queryMatchesDescription() {
        Skill a = mk(1L, "Alpha", "alpha", "tool", "hook");
        a.setDescription("专业绘画工具");
        Skill b = mk(2L, "Beta", "beta", "tool", "hook");
        b.setDescription("无关内容");
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list("绘画", null, null, null);

        assertEquals(1, result.size());
        assertEquals("Alpha", result.get(0).getName());
    }

    @Test
    void list_queryMatchesSlug() {
        Skill a = mk(1L, "Alpha", "my-slug-here", "tool", "hook");
        a.setDescription("none");
        Skill b = mk(2L, "Beta", "other", "tool", "hook");
        b.setDescription("none");
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list("slug-here", null, null, null);

        assertEquals(1, result.size());
        assertEquals("my-slug-here", result.get(0).getSlug());
    }

    @Test
    void list_tagFilter_skipsNullTags() {
        Skill a = mk(1L, "Alpha", "alpha", "tool", null);
        Skill b = mk(2L, "Beta", "beta", "tool", "hook");
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list(null, "hook", null, null);

        assertEquals(1, result.size());
        assertEquals("Beta", result.get(0).getName());
    }

    @Test
    void list_tagFilter_trimsSpaces() {
        Skill a = mk(1L, "Alpha", "alpha", "tool", "a, b");
        Skill b = mk(2L, "Beta", "beta", "tool", "c, d");
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list(null, "b", null, null);

        assertEquals(1, result.size());
        assertEquals("Alpha", result.get(0).getName());
    }

    @Test
    void list_blankCategory_noFiltering() {
        Skill a = mk(1L, "Alpha", "alpha", "tool", "hook");
        Skill b = mk(2L, "Beta", "beta", "game", "hook");
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list(null, null, "", null);

        assertEquals(2, result.size());
    }

    @Test
    void list_sortRating_nullAvgLast() {
        Skill a = mk(1L, "Alpha", "alpha", "tool", "hook");
        Skill b = mk(2L, "Beta", "beta", "tool", "hook");
        b.setRatingSum(9L); b.setRatingCount(2L);
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list(null, null, null, "rating");

        assertEquals(2, result.size());
        assertEquals("Beta", result.get(0).getName());
        assertEquals("Alpha", result.get(1).getName());
    }

    @Test
    void list_sortNewest() {
        Skill a = mk(1L, "Alpha", "alpha", "tool", "hook");
        a.setCreatedAt(LocalDateTime.of(2026, 1, 1, 0, 0));
        Skill b = mk(2L, "Beta", "beta", "tool", "hook");
        b.setCreatedAt(LocalDateTime.of(2026, 6, 1, 0, 0));
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list(null, null, null, "newest");

        assertEquals(2, result.size());
        assertEquals("Beta", result.get(0).getName());
        assertEquals("Alpha", result.get(1).getName());
    }

    @Test
    void list_sortName() {
        Skill a = mk(1L, "Beta", "beta", "tool", "hook");
        Skill b = mk(2L, "Alpha", "alpha", "tool", "hook");
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list(null, null, null, "name");

        assertEquals(2, result.size());
        assertEquals("Alpha", result.get(0).getName());
        assertEquals("Beta", result.get(1).getName());
    }

    @Test
    void list_unknownSort_fallsBackToPopular() {
        Skill a = mk(1L, "Alpha", "alpha", "tool", "hook");
        a.setInstallCount(10L);
        Skill b = mk(2L, "Beta", "beta", "tool", "hook");
        b.setInstallCount(99L);
        when(skillRepository.findAll()).thenReturn(List.of(a, b));

        List<Skill> result = skillService.list(null, null, null, "weird");

        assertEquals(2, result.size());
        assertEquals("Beta", result.get(0).getName());
        assertEquals(Long.valueOf(99), result.get(0).getInstallCount());
        assertTrue(result.get(1).getInstallCount() < result.get(0).getInstallCount());
    }
}
