package com.dramafactory.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;


import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SkillHubInstallFlowTest {

    private static final String SKILL_ID = "video-sync";

    @Autowired
    private MockMvc mockMvc;

    private final ObjectMapper objectMapper = new ObjectMapper();

    static Path skillsTempDir;

    @DynamicPropertySource
    static void skillsDir(DynamicPropertyRegistry registry) throws Exception {
        skillsTempDir = Files.createTempDirectory("drama-skills-");
        registry.add("drama.skills.dir", () -> skillsTempDir.toString());
    }

    @BeforeEach
    void cleanSkillsDir() throws Exception {
        if (skillsTempDir == null) {
            return;
        }
        try (Stream<Path> stream = Files.list(skillsTempDir)) {
            for (Path child : stream.sorted(Comparator.reverseOrder()).toList()) {
                deleteRecursively(child);
            }
        }
    }

    private static void deleteRecursively(Path path) throws Exception {
        if (Files.isDirectory(path)) {
            try (Stream<Path> stream = Files.list(path)) {
                for (Path child : stream.sorted(Comparator.reverseOrder()).toList()) {
                    deleteRecursively(child);
                }
            }
        }
        Files.deleteIfExists(path);
    }


    private JsonNode getHubIndex() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/skillhub/index").param("q", SKILL_ID))
                .andExpect(status().isOk())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    private JsonNode findSkill(JsonNode index, String id) {
        JsonNode skills = index.get("skills");
        assertNotNull(skills, "index.skills 不能为空");
        for (JsonNode skill : skills) {
            if (id.equals(skill.path("id").asText())) {
                return skill;
            }
        }
        return null;
    }

    private MvcResult installSkill(String id) throws Exception {
        return mockMvc.perform(post("/api/official-skills/install/" + id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andReturn();
    }

    @Test
    void installFlowViaHubIndex() throws Exception {
        JsonNode beforeIndex = getHubIndex();
        JsonNode beforeSkill = findSkill(beforeIndex, SKILL_ID);
        assertNotNull(beforeSkill, "hub index 中应存在 " + SKILL_ID + " 条目");
        assertFalse(beforeSkill.path("installed").asBoolean(), "安装前 " + SKILL_ID + " 应为未安装");

        MvcResult installResult = installSkill(SKILL_ID);
        assertEquals(200, installResult.getResponse().getStatus(),
                "安装 " + SKILL_ID + " 应返回 200");
        JsonNode installBody = objectMapper.readTree(installResult.getResponse().getContentAsString(StandardCharsets.UTF_8));
        assertEquals(SKILL_ID, installBody.path("id").asText());
        assertFalse(installBody.path("alreadyInstalled").asBoolean(),
                "首次安装 alreadyInstalled 应为 false");

        JsonNode afterIndex = getHubIndex();
        JsonNode afterSkill = findSkill(afterIndex, SKILL_ID);
        assertNotNull(afterSkill, "安装后 hub index 中仍应存在 " + SKILL_ID + " 条目");
        assertTrue(afterSkill.path("installed").asBoolean(), "安装后 " + SKILL_ID + " 应为已安装");
        assertNotNull(afterSkill.get("installedVersion"), "installedVersion 字段应存在");
        assertFalse(afterSkill.path("installedVersion").asText().isEmpty(),
                "安装后 installedVersion 不应为空");
    }

    @Test
    void installIsIdempotentViaHubIndex() throws Exception {
        MvcResult firstInstall = installSkill(SKILL_ID);
        assertEquals(200, firstInstall.getResponse().getStatus(),
                "首次安装 " + SKILL_ID + " 应返回 200");
        JsonNode firstBody = objectMapper.readTree(firstInstall.getResponse().getContentAsString(StandardCharsets.UTF_8));
        assertEquals(SKILL_ID, firstBody.path("id").asText());
        assertFalse(firstBody.path("alreadyInstalled").asBoolean(),
                "首次安装 alreadyInstalled 应为 false");

        MvcResult secondInstall = installSkill(SKILL_ID);
        assertEquals(200, secondInstall.getResponse().getStatus(),
                "重复安装 " + SKILL_ID + " 应返回 200");
        JsonNode secondBody = objectMapper.readTree(secondInstall.getResponse().getContentAsString(StandardCharsets.UTF_8));
        assertEquals(SKILL_ID, secondBody.path("id").asText());
        assertTrue(secondBody.path("alreadyInstalled").asBoolean(),
                "重复安装 alreadyInstalled 应为 true");

        JsonNode index = getHubIndex();
        JsonNode skill = findSkill(index, SKILL_ID);
        assertNotNull(skill, "hub index 中应存在 " + SKILL_ID + " 条目");
        assertTrue(skill.path("installed").asBoolean(), "重复安装后 " + SKILL_ID + " 仍应为已安装");
    }

    @Test
    void installUnknownSkillFails() throws Exception {
        MvcResult result = installSkill("no-such-skill-xyz");
        int statusCode = result.getResponse().getStatus();
        assertTrue(statusCode >= 400 && statusCode <= 599,
                "安装未知 skill 应返回 4xx 或 5xx，实际状态码: " + statusCode);
    }

    @Test
    void hubIndexStaysConsistentAfterInstall() throws Exception {
        JsonNode beforeIndex = getHubIndex();
        int beforeCount = beforeIndex.path("skills").size();
        JsonNode beforeSkill = findSkill(beforeIndex, SKILL_ID);
        assertNotNull(beforeSkill, "hub index 中应存在 " + SKILL_ID + " 条目");
        String beforeSource = beforeSkill.path("source").asText();

        MvcResult installResult = installSkill(SKILL_ID);
        assertEquals(200, installResult.getResponse().getStatus(),
                "安装 " + SKILL_ID + " 应返回 200");

        JsonNode afterIndex = getHubIndex();
        int afterCount = afterIndex.path("skills").size();
        assertEquals(beforeCount, afterCount, "安装前后 hub index skills 总数应保持一致");

        JsonNode afterSkill = findSkill(afterIndex, SKILL_ID);
        assertNotNull(afterSkill, "安装后 hub index 中仍应存在 " + SKILL_ID + " 条目");
        assertEquals("社区收录", afterSkill.path("source").asText(),
                "安装不应改变 " + SKILL_ID + " 的来源标注");
        assertEquals(beforeSource, afterSkill.path("source").asText(),
                "安装前后 source 字段应保持一致");
    }
}
