package com.dramafactory.controller;

import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillInstall;
import com.dramafactory.model.SkillRating;
import com.dramafactory.model.SkillVersion;
import com.dramafactory.repository.SkillRatingRepository;
import com.dramafactory.repository.SkillVersionRepository;
import com.dramafactory.service.SkillService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * SkillController 单元测试（mock SkillService + 两个 Repository）。
 */
class SkillControllerTest {

    private SkillService skillService;
    private SkillVersionRepository skillVersionRepository;
    private SkillRatingRepository skillRatingRepository;
    private SkillController controller;

    @BeforeEach
    void setUp() {
        skillService = mock(SkillService.class);
        skillVersionRepository = mock(SkillVersionRepository.class);
        skillRatingRepository = mock(SkillRatingRepository.class);
        controller = new SkillController(skillService, skillVersionRepository, skillRatingRepository);
    }

    private Skill sampleSkill(long id, String name, String slug) {
        Skill s = new Skill();
        s.setId(id);
        s.setName(name);
        s.setSlug(slug);
        s.setInstallCount(3L);
        s.setRatingSum(9L);
        s.setRatingCount(2L);
        return s;
    }

    private SkillVersion sampleVersion(long skillId, String version) {
        SkillVersion v = new SkillVersion();
        v.setSkillId(skillId);
        v.setVersion(version);
        v.setPromptTemplate("pt");
        return v;
    }

    private SkillService.SkillDetail sampleDetail(Skill s, String installedVersion) {
        return new SkillService.SkillDetail(s, List.of(sampleVersion(s.getId(), "1.0.0")),
                installedVersion, s.getAvgRating());
    }

    @Test
    void list_returnsDtos() {
        Skill s = sampleSkill(1L, "技能A", "skill-a");
        when(skillService.list(any(), any(), any(), any())).thenReturn(List.of(s));
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L))
                .thenReturn(List.of(sampleVersion(1L, "1.0.0")));
        when(skillService.getDetail(1L)).thenReturn(sampleDetail(s, null));

        List<SkillController.SkillDto> dtos = controller.list(null, null, null, null);

        assertEquals(1, dtos.size());
        SkillController.SkillDto dto = dtos.get(0);
        assertEquals(1L, dto.id());
        assertEquals("技能A", dto.name());
        assertEquals("skill-a", dto.slug());
        assertEquals(3L, dto.installCount());
        assertEquals(4.5, dto.avgRating());
        assertEquals("1.0.0", dto.latestVersion());
        assertNull(dto.installedVersion());
    }

    @Test
    void publish_returnsDto() {
        Skill s = sampleSkill(5L, "新技能", "new-skill");
        when(skillService.publish(eq("新技能"), eq("new-skill"), any(), any(),
                any(), any(), any(), any(), any())).thenReturn(s);
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(5L))
                .thenReturn(List.of(sampleVersion(5L, "1.0.0")));

        SkillController.CreateSkillRequest req = new SkillController.CreateSkillRequest(
                "新技能", "new-skill", "d", "a", "SCRIPT", "t", "i", "pt", "c");

        SkillController.SkillDto dto = controller.publish(req);

        assertEquals("新技能", dto.name());
        assertEquals("new-skill", dto.slug());
        assertEquals("1.0.0", dto.latestVersion());
    }

    @Test
    void get_returnsDetail() {
        Skill s = sampleSkill(2L, "详情技能", "detail-skill");
        when(skillService.getDetail(2L)).thenReturn(sampleDetail(s, "1.0.0"));
        when(skillRatingRepository.findBySkillIdOrderByCreatedAtDesc(2L)).thenReturn(List.of());

        SkillController.SkillDetailDto dto = controller.get(2L);

        assertEquals("详情技能", dto.name());
        assertEquals("1.0.0", dto.installedVersion());
        assertNotNull(dto.versions());
        assertEquals(1, dto.versions().size());
    }

    @Test
    void install_uninstall_rate_render() {
        SkillInstall install = new SkillInstall();
        install.setSkillId(1L);
        install.setVersion("1.0.0");
        when(skillService.install(1L, "1.0.0")).thenReturn(install);

        SkillController.InstallDto installDto =
                controller.install(1L, new SkillController.InstallRequest("1.0.0"));
        assertEquals("1.0.0", installDto.version());

        doNothing().when(skillService).uninstall(1L);
        controller.uninstall(1L);
        verify(skillService).uninstall(1L);

        SkillRating rating = new SkillRating();
        rating.setSkillId(1L);
        rating.setScore(5);
        when(skillService.rate(1L, 5, "好")).thenReturn(rating);
        SkillController.RatingDto ratingDto =
                controller.rate(1L, new SkillController.RateRequest(5, "好"));
        assertEquals(5, ratingDto.score());

        when(skillService.renderTemplate(eq(1L), eq("1.0.0"), anyMap()))
                .thenReturn("rendered");
        SkillController.RenderResponse renderResponse = controller.render(1L,
                new SkillController.RenderRequest("1.0.0", Map.of("x", "1")));
        assertEquals("rendered", renderResponse.content());
    }

    @Test
    void publish_invalidInput_propagates() {
        when(skillService.publish(any(), any(), any(), any(), any(), any(), any(), any(), any()))
                .thenThrow(new IllegalArgumentException("bad slug"));

        SkillController.CreateSkillRequest req = new SkillController.CreateSkillRequest(
                "n", "BAD SLUG", "d", "a", "SCRIPT", "t", "i", "pt", "c");

        assertThrows(IllegalArgumentException.class, () -> controller.publish(req));
    }
}
