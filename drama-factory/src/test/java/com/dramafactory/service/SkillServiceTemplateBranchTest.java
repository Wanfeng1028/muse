// SkillService renderTemplate/resolveForUse/installedList 分支覆盖（v2.14）
package com.dramafactory.service;

import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillInstall;
import com.dramafactory.model.SkillVersion;
import com.dramafactory.repository.SkillInstallRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.repository.SkillVersionRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SkillServiceTemplateBranchTest {

    @Mock
    private SkillRepository skillRepository;

    @Mock
    private SkillVersionRepository skillVersionRepository;

    @Mock
    private SkillInstallRepository skillInstallRepository;

    @InjectMocks
    private SkillService skillService;

    private Skill skill(Long id, String name) {
        Skill s = new Skill();
        s.setId(id);
        s.setName(name);
        return s;
    }

    private SkillVersion version(Long skillId, String ver, String template) {
        SkillVersion v = new SkillVersion();
        v.setSkillId(skillId);
        v.setVersion(ver);
        v.setPromptTemplate(template);
        return v;
    }

    private SkillInstall install(Long skillId, String ver) {
        SkillInstall i = new SkillInstall();
        i.setSkillId(skillId);
        i.setVersion(ver);
        return i;
    }

    @Test
    void renderTemplate_blankVersion_usesLatest() {
        Skill s = skill(1L, "n");
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s));

        SkillVersion latest = version(1L, "1.0.1", "A{{x}}");
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L))
                .thenReturn(List.of(latest));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.1"))
                .thenReturn(Optional.of(latest));

        String result = skillService.renderTemplate(1L, "", Map.of("x", "1"));

        assertEquals("A1", result);
    }

    @Test
    void renderTemplate_versionNotFound_throws() {
        Skill s = skill(1L, "n");
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s));

        when(skillVersionRepository.findBySkillIdAndVersion(1L, "9.9.9"))
                .thenReturn(Optional.empty());

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.renderTemplate(1L, "9.9.9", Map.of()));

        assertTrue(ex.getMessage().contains("版本不存在"),
                "异常消息应包含关键字：版本不存在，实际=" + ex.getMessage());
    }

    @Test
    void renderTemplate_nullTemplate_returnsEmpty() {
        Skill s = skill(1L, "n");
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s));

        SkillVersion v = version(1L, "1.0.0", null);
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.0"))
                .thenReturn(Optional.of(v));

        String result = skillService.renderTemplate(1L, "1.0.0", Map.of("x", "1"));

        assertEquals("", result);
    }

    @Test
    void renderTemplate_nullVariables_keepsPlaceholder() {
        Skill s = skill(1L, "n");
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s));

        SkillVersion v = version(1L, "1.0.0", "A{{x}}B");
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.0"))
                .thenReturn(Optional.of(v));

        String result = skillService.renderTemplate(1L, "1.0.0", null);

        assertEquals("A{{x}}B", result);
    }

    @Test
    void resolveForUse_happy() {
        Skill s = skill(1L, "HelloSkill");
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s));

        SkillInstall inst = install(1L, "1.0.0");
        when(skillInstallRepository.findBySkillId(1L)).thenReturn(Optional.of(inst));

        SkillVersion v = version(1L, "1.0.0", "Hi {{who}}");
        when(skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(1L))
                .thenReturn(List.of(v));
        when(skillVersionRepository.findBySkillIdAndVersion(1L, "1.0.0"))
                .thenReturn(Optional.of(v));

        SkillService.ResolvedSkill resolved = skillService.resolveForUse(1L, Map.of("who", "Tom"));

        assertEquals("1.0.0", resolved.version());
        assertEquals("Hi Tom", resolved.renderedPrompt());
        assertEquals("HelloSkill", resolved.name());
    }

    @Test
    void installedList_skipsMissingSkill() {
        SkillInstall i1 = install(1L, "1.0.0");
        SkillInstall i2 = install(2L, "2.0.0");
        when(skillInstallRepository.findAllByOrderByInstalledAtDesc())
                .thenReturn(List.of(i1, i2));

        Skill s1 = skill(1L, "n1");
        when(skillRepository.findById(1L)).thenReturn(Optional.of(s1));
        when(skillRepository.findById(2L)).thenReturn(Optional.empty());

        List<SkillService.InstalledSkill> result = skillService.installedList();

        assertEquals(1, result.size());
        assertEquals(1L, result.get(0).skill().getId());
    }
}
