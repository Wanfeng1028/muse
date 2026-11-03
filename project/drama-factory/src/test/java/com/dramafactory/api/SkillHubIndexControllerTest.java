package com.dramafactory.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SkillHubIndexControllerTest {

    @Autowired
    private MockMvc mockMvc;

    static Path SKILLS_TMP;

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry r) {
        try {
            SKILLS_TMP = Files.createTempDirectory("skills-test");
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        r.add("drama.skills.dir", () -> SKILLS_TMP.toString());
    }

    @Test
    void indexReturnsHubMetadata() throws Exception {
        mockMvc.perform(get("/api/skillhub/index"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.hub", is("playhouse-skillhub")))
                .andExpect(jsonPath("$.version", is(1)))
                .andExpect(jsonPath("$.updatedAt", not(emptyOrNullString())));
    }

    @Test
    void indexListsRealSkillsWithSourceLabels() throws Exception {
        org.springframework.test.web.servlet.MvcResult result = mockMvc.perform(get("/api/skillhub/index"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills.length()", is(50)))
                .andReturn();
        com.fasterxml.jackson.databind.JsonNode root = new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(result.getResponse().getContentAsString());
        java.util.List<String> ids = new java.util.ArrayList<>();
        for (com.fasterxml.jackson.databind.JsonNode skill : root.get("skills")) {
            ids.add(skill.get("id").asText());
        }
        org.junit.jupiter.api.Assertions.assertFalse(ids.isEmpty());
        java.util.List<String> sorted = new java.util.ArrayList<>(ids);
        java.util.Collections.sort(sorted);
        org.junit.jupiter.api.Assertions.assertEquals(sorted, ids);

        mockMvc.perform(get("/api/skillhub/index").param("q", "video-shots"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[?(@.id=='video-shots')].source", contains("社区收录")))
                .andExpect(jsonPath("$.skills[?(@.id=='video-shots')].license", contains("Apache-2.0")));
        mockMvc.perform(get("/api/skillhub/index").param("q", "toonflow-canvas"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[?(@.id=='toonflow-canvas')].source", contains("社区收录")));
        mockMvc.perform(get("/api/skillhub/index").param("q", "watzing-video-editor"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[?(@.id=='watzing-video-editor')].source", contains("社区收录")));
    }

    @Test
    void installableAlwaysTrue() throws Exception {
        mockMvc.perform(get("/api/skillhub/index"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[0].installable", is(true)))
                .andExpect(jsonPath("$.skills[1].installable", is(true)))
                .andExpect(jsonPath("$.skills[2].installable", is(true)));
    }

    @Test
    void installedFlagFlipsAfterInstall() throws Exception {
        mockMvc.perform(get("/api/skillhub/index").param("q", "video-scrub"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[?(@.id=='video-scrub')].installed", contains(false)));

        mockMvc.perform(post("/api/official-skills/install/video-scrub")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/skillhub/index").param("q", "video-scrub"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[?(@.id=='video-scrub')].installed", contains(true)))
                .andExpect(jsonPath("$.skills[?(@.id=='video-scrub')].installedVersion", contains(not(emptyOrNullString()))));
    }

    @Test
    void installedFlagFlipsAfterInstallForEmptyVersionSkill() throws Exception {
        // 02ui-video-copy 的 bundled 版本号本身为空串：装完后 installedVersion
        // 仍为空，但 installed 必须翻转为 true（回归：旧写法以版本号非空判断）。
        mockMvc.perform(get("/api/skillhub/index").param("q", "02ui-video-copy"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[?(@.id=='02ui-video-copy')].installed", contains(false)));

        mockMvc.perform(post("/api/official-skills/install/02ui-video-copy")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/skillhub/index").param("q", "02ui-video-copy"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[?(@.id=='02ui-video-copy')].installed", contains(true)))
                .andExpect(jsonPath("$.skills[?(@.id=='02ui-video-copy')].installedVersion").exists());
    }

    @Test
    void noNullStringFields() throws Exception {
        mockMvc.perform(get("/api/skillhub/index"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[0].description").exists())
                .andExpect(jsonPath("$.skills[0].sourceUrl").exists())
                .andExpect(jsonPath("$.skills[0].installedVersion").exists())
                .andExpect(jsonPath("$.skills[1].description").exists())
                .andExpect(jsonPath("$.skills[1].sourceUrl").exists())
                .andExpect(jsonPath("$.skills[1].installedVersion").exists())
                .andExpect(jsonPath("$.skills[2].description").exists())
                .andExpect(jsonPath("$.skills[2].sourceUrl").exists())
                .andExpect(jsonPath("$.skills[2].installedVersion").exists())
                .andExpect(jsonPath("$.skills[3].description").exists())
                .andExpect(jsonPath("$.skills[3].sourceUrl").exists())
                .andExpect(jsonPath("$.skills[3].installedVersion").exists())
                .andExpect(jsonPath("$.skills[4].description").exists())
                .andExpect(jsonPath("$.skills[4].sourceUrl").exists())
                .andExpect(jsonPath("$.skills[4].installedVersion").exists());
    }
}