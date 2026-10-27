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

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SkillHubIndexPaginationValidationTest {

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
    void size201Returns400() throws Exception {
        mockMvc.perform(get("/api/skillhub/index").param("size", "201"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void size200Ok() throws Exception {
        mockMvc.perform(get("/api/skillhub/index").param("size", "200"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.size").value(200));
    }

    @Test
    void size1Ok() throws Exception {
        mockMvc.perform(get("/api/skillhub/index").param("size", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.size").value(1))
                .andExpect(jsonPath("$.skills.length()").value(1));
    }

    @Test
    void negativeSizeReturns400() throws Exception {
        mockMvc.perform(get("/api/skillhub/index").param("size", "-1"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void sizeAbcReturns400() throws Exception {
        mockMvc.perform(get("/api/skillhub/index").param("size", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void pageAbcReturns400() throws Exception {
        mockMvc.perform(get("/api/skillhub/index").param("page", "abc"))
                .andExpect(status().isBadRequest());
    }
}
