package com.dramafactory.controller;

import com.dramafactory.service.skill.SkillHubClient;
import static org.hamcrest.Matchers.hasSize;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.result.MockMvcResultMatchers;
import org.hamcrest.Matchers;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:officialskill;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"})
class OfficialSkillRestoredDeepR2Test {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private SkillHubClient hubClient;

    @Test
    void officialReturnsOkAndJsonArray() throws Exception {
        when(hubClient.isEnabled()).thenReturn(false);
        mockMvc.perform(get("/api/official-skills/official"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    void officialBundledSkillsAreNonEmptyAndAllBundled() throws Exception {
        when(hubClient.isEnabled()).thenReturn(false);
        // 技能库在持续扩充，不硬编码数量：只断言非空且全部为 bundled 来源
        mockMvc.perform(get("/api/official-skills/official"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.length()").value(org.hamcrest.Matchers.greaterThan(500)))
                .andExpect(jsonPath("$[?(@.source != 'bundled')]").isEmpty());
    }

    @Test
    void officialContainsWaoowaooCreativeCoreWithElasticLicense() throws Exception {
        when(hubClient.isEnabled()).thenReturn(false);
        mockMvc.perform(get("/api/official-skills/official"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.id == 'waoowaoo-creative-core')].license").value("Elastic License 2.0"));
    }

    @Test
    void officialHas7HuobaoSkills() throws Exception {
        when(hubClient.isEnabled()).thenReturn(false);
        mockMvc.perform(get("/api/official-skills/official"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.id =~ /.*huobao.*/i)]").value(hasSize(7)));
    }

    @Test
    void officialWatzingVideoEditorHasNoassertionLicense() throws Exception {
        when(hubClient.isEnabled()).thenReturn(false);
        mockMvc.perform(get("/api/official-skills/official"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.id == 'watzing-video-editor')].license").value("NOASSERTION"));
    }

    @Test
    void officialNoLicenseContainsRewritten() throws Exception {
        when(hubClient.isEnabled()).thenReturn(false);
        mockMvc.perform(get("/api/official-skills/official"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.license =~ /.*\\(rewritten\\).*/)]").value(hasSize(0)));
    }

    @Test
    void officialTalkingHeadGuideHasAgplLicense() throws Exception {
        when(hubClient.isEnabled()).thenReturn(false);
        mockMvc.perform(get("/api/official-skills/official"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.id == 'talking-head-guide')].license").value("AGPL-3.0"));
    }

    @Test
    void installedReturnsOk() throws Exception {
        mockMvc.perform(get("/api/official-skills/installed"))
                .andExpect(status().isOk());
    }
}
