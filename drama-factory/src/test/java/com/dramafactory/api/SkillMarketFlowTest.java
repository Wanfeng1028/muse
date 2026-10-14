package com.dramafactory.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SkillMarketFlowTest {

    @Autowired private MockMvc mockMvc;

    private final ObjectMapper om = new ObjectMapper();

    private String createBody(String name, String slug) {
        return "{\"name\":\"" + name + "\",\"slug\":\"" + slug + "\","
                + "\"description\":\"desc\",\"author\":\"me\",\"category\":\"SCRIPT\","
                + "\"tags\":\"a,b\",\"icon\":\"i\",\"promptTemplate\":\"P {{x}}\","
                + "\"changelog\":\"init\"}";
    }

    @Test
    void publish_install_rate_upgrade_uninstall_flow() throws Exception {
        String slug = "flow-" + System.nanoTime();

        MvcResult created = mockMvc.perform(post("/api/skills")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("流程技能", slug)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").exists())
                .andReturn();

        long id = om.readTree(created.getResponse().getContentAsString()).get("id").asLong();

        mockMvc.perform(post("/api/skills/" + id + "/versions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"version\":\"1.0.1\",\"promptTemplate\":\"P2 {{x}}\",\"changelog\":\"up\"}"))
                .andExpect(status().isCreated());

        mockMvc.perform(get("/api/skills").param("q", slug))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].slug").value(slug));

        mockMvc.perform(post("/api/skills/" + id + "/install")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"version\":\"1.0.1\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("1.0.1"));

        mockMvc.perform(get("/api/skills/installed"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].skill.slug").value(slug));

        mockMvc.perform(post("/api/skills/" + id + "/rate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"score\":5,\"comment\":\"好\"}"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/skills/" + id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.installedVersion").value("1.0.1"))
                .andExpect(jsonPath("$.avgRating").value(5.0));

        mockMvc.perform(post("/api/skills/" + id + "/install")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"version\":\"1.0.0\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("1.0.0"));

        mockMvc.perform(delete("/api/skills/" + id + "/install"))
                .andExpect(status().isNoContent());
        mockMvc.perform(delete("/api/skills/" + id + "/install"))
                .andExpect(status().isNotFound());
    }

    @Test
    void category_filter_works() throws Exception {
        // 注意：测试库 ddl-auto=create-drop，不跑 Flyway seed；此处自建数据验证筛选
        String slugA = "cat-a-" + System.nanoTime();
        String slugB = "cat-b-" + System.nanoTime();
        mockMvc.perform(post("/api/skills")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("分类A", slugA)))
                .andExpect(status().isCreated());
        String bodyB = createBody("分类B", slugB).replace("\"category\":\"SCRIPT\"", "\"category\":\"BOARD\"");
        mockMvc.perform(post("/api/skills")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(bodyB))
                .andExpect(status().isCreated());

        mockMvc.perform(get("/api/skills").param("category", "SCRIPT"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString(slugA)))
                .andExpect(content().string(org.hamcrest.Matchers.not(containsString(slugB))));

        mockMvc.perform(get("/api/skills").param("category", "BOARD"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString(slugB)));
    }

    @Test
    void publish_duplicateSlug_returns400() throws Exception {
        String slug = "dup-" + System.nanoTime();
        mockMvc.perform(post("/api/skills")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("第一次", slug)))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/api/skills")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("第二次", slug)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rate_invalidScore_returns400() throws Exception {
        String slug = "rate-" + System.nanoTime();
        MvcResult created = mockMvc.perform(post("/api/skills")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("评分技能", slug)))
                .andExpect(status().isCreated())
                .andReturn();
        long id = om.readTree(created.getResponse().getContentAsString()).get("id").asLong();

        mockMvc.perform(post("/api/skills/" + id + "/rate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"score\":9,\"comment\":\"bad\"}"))
                .andExpect(status().isBadRequest());
    }
}
