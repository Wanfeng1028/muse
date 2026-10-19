package com.dramafactory.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OfficialSkillControllerTest {

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
    void officialListsBundledSkills() throws Exception {
        mockMvc.perform(get("/api/official-skills/official"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(35))
                .andExpect(jsonPath("$[?(@.id=='video-shots')].license").value(hasItem("Apache-2.0")))
                .andExpect(jsonPath("$[?(@.id=='video-shots')].source").value(hasItem("bundled")))
                .andExpect(jsonPath("$[?(@.id=='video-shots')].installed").value(hasItem(false)))
                .andExpect(jsonPath("$[?(@.id=='watzing-video-editor')].installable").value(hasItem(true)))
                .andExpect(jsonPath("$[?(@.id=='watzing-video-editor')].sourceUrl").value(hasItem("https://github.com/watzing/claude-video-editor")))
                .andExpect(jsonPath("$[?(@.id=='video-shots')].installable").value(hasItem(true)));
    }

    @Test
    void installRewrittenSkillReturns200() throws Exception {
        mockMvc.perform(post("/api/official-skills/install/openmontage-video-edit")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("openmontage-video-edit"))
                .andExpect(jsonPath("$.source").value("bundled"));
    }

    @Test
    void installBundledSkill() throws Exception {
        mockMvc.perform(post("/api/official-skills/install/video-scrub")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("video-scrub"))
                .andExpect(jsonPath("$.alreadyInstalled").value(false))
                .andExpect(jsonPath("$.source").value("bundled"));

        mockMvc.perform(get("/api/official-skills/installed"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.id=='video-scrub')]").value(hasSize(1)));

        mockMvc.perform(post("/api/official-skills/install/video-scrub")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.alreadyInstalled").value(true));
    }

    @Test
    void installUnknownSkillReturns400() throws Exception {
        mockMvc.perform(post("/api/official-skills/install/no-such-xyz")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void uninstallSkill() throws Exception {
        mockMvc.perform(post("/api/official-skills/install/video-sync")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isOk());

        mockMvc.perform(delete("/api/official-skills/installed/video-sync"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.removed").value(true));

        mockMvc.perform(delete("/api/official-skills/installed/video-sync"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.removed").value(false));

        mockMvc.perform(get("/api/official-skills/installed"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.id=='video-sync')]").value(hasSize(0)));
    }
}
