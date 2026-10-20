package com.dramafactory.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.hamcrest.Matchers.*;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SkillHubPaginationTest {

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
    void noParamsReturnsAll() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/skillhub/index"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page", is(0)))
                .andExpect(jsonPath("$.totalPages", is(1)))
                .andReturn();
        String body = result.getResponse().getContentAsString(StandardCharsets.UTF_8);
        int total = com.jayway.jsonpath.JsonPath.read(body, "$.total");
        int size = com.jayway.jsonpath.JsonPath.read(body, "$.size");
        int len = com.jayway.jsonpath.JsonPath.read(body, "$.skills.length()");
        assertTrue(total >= 200, "expected at least 200 skills, got " + total);
        assertTrue(total == len && size == total, "size should equal total when no params");
    }

    @Test
    void firstPageSizeTen() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/skillhub/index").param("page", "0").param("size", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page", is(0)))
                .andExpect(jsonPath("$.size", is(10)))
                .andExpect(jsonPath("$.skills.length()", is(10)))
                .andReturn();
        String body = result.getResponse().getContentAsString(StandardCharsets.UTF_8);
        int total = com.jayway.jsonpath.JsonPath.read(body, "$.total");
        int totalPages = com.jayway.jsonpath.JsonPath.read(body, "$.totalPages");
        assertTrue(totalPages == (total + 9) / 10, "totalPages should be ceil(total/10)");
    }

    @Test
    void secondPageNoOverlap() throws Exception {
        MvcResult r0 = mockMvc.perform(get("/api/skillhub/index").param("page", "0").param("size", "10"))
            .andExpect(status().isOk()).andReturn();
        String body0 = r0.getResponse().getContentAsString(StandardCharsets.UTF_8);
        List<String> ids0 = com.jayway.jsonpath.JsonPath.read(body0, "$.skills[*].id");
    
        MvcResult r1 = mockMvc.perform(get("/api/skillhub/index").param("page", "1").param("size", "10"))
            .andExpect(status().isOk()).andReturn();
        String body1 = r1.getResponse().getContentAsString(StandardCharsets.UTF_8);
        List<String> ids1 = com.jayway.jsonpath.JsonPath.read(body1, "$.skills[*].id");
    
        assertTrue(Collections.disjoint(ids0, ids1));
    }
    @Test
    void pageOutOfRangeEmpty() throws Exception {
        MvcResult r = mockMvc.perform(get("/api/skillhub/index").param("page", "99999").param("size", "10"))
            .andExpect(status().isOk()).andReturn();
        String body = r.getResponse().getContentAsString(StandardCharsets.UTF_8);
        int length = com.jayway.jsonpath.JsonPath.read(body, "$.skills.length()");
        assertEquals(0, length);
    }
    @Test
    void sizeClampedTo200() throws Exception {
        MvcResult r = mockMvc.perform(get("/api/skillhub/index").param("size", "500"))
            .andExpect(status().isOk()).andReturn();
        String body = r.getResponse().getContentAsString(StandardCharsets.UTF_8);
        int size = com.jayway.jsonpath.JsonPath.read(body, "$.size");
        assertEquals(200, size);
    }
    @Test
    void sizeZeroClampedToOne() throws Exception {
        MvcResult r = mockMvc.perform(get("/api/skillhub/index").param("size", "0"))
            .andExpect(status().isOk()).andReturn();
        String body = r.getResponse().getContentAsString(StandardCharsets.UTF_8);
        int size = com.jayway.jsonpath.JsonPath.read(body, "$.size");
        assertEquals(1, size);
    }
    @Test
    void negativePageAsZero() throws Exception {
        MvcResult rNeg = mockMvc.perform(get("/api/skillhub/index").param("page", "-1").param("size", "10"))
            .andExpect(status().isOk()).andReturn();
        String bodyNeg = rNeg.getResponse().getContentAsString(StandardCharsets.UTF_8);
        String firstIdNeg = com.jayway.jsonpath.JsonPath.read(bodyNeg, "$.skills[0].id");
    
        MvcResult rZero = mockMvc.perform(get("/api/skillhub/index").param("page", "0").param("size", "10"))
            .andExpect(status().isOk()).andReturn();
        String bodyZero = rZero.getResponse().getContentAsString(StandardCharsets.UTF_8);
        String firstIdZero = com.jayway.jsonpath.JsonPath.read(bodyZero, "$.skills[0].id");
    
        assertEquals(firstIdZero, firstIdNeg);
    }
    @Test
    void queryFilters() throws Exception {
        MvcResult rAll = mockMvc.perform(get("/api/skillhub/index"))
            .andExpect(status().isOk()).andReturn();
        String bodyAll = rAll.getResponse().getContentAsString(StandardCharsets.UTF_8);
        int totalAll = com.jayway.jsonpath.JsonPath.read(bodyAll, "$.total");
    
        MvcResult rQuery = mockMvc.perform(get("/api/skillhub/index").param("q", "video"))
            .andExpect(status().isOk()).andReturn();
        String bodyQuery = rQuery.getResponse().getContentAsString(StandardCharsets.UTF_8);
        int totalQuery = com.jayway.jsonpath.JsonPath.read(bodyQuery, "$.total");
    
        assertTrue(totalQuery < totalAll);
    }
    @Test
    void sourceFilter() throws Exception {
        MvcResult r = mockMvc.perform(get("/api/skillhub/index").param("source", "官方出品"))
            .andExpect(status().isOk()).andReturn();
        String body = r.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8);
        List<String> sources = com.jayway.jsonpath.JsonPath.read(body, "$.skills[*].source");
        for (String source : sources) {
            assertEquals("官方出品", source);
        }
    }
    @Test
    void queryWithPage() throws Exception {
        MvcResult r = mockMvc.perform(get("/api/skillhub/index").param("q", "video").param("page", "1").param("size", "5"))
            .andExpect(status().isOk()).andReturn();
        String body = r.getResponse().getContentAsString(StandardCharsets.UTF_8);
        int page = com.jayway.jsonpath.JsonPath.read(body, "$.page");
        assertEquals(1, page);
    }
}
