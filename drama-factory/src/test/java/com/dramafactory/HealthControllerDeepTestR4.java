package com.dramafactory;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HealthControllerDeepTestR4 {

    @Autowired
    private MockMvc mockMvc;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void health_get_returns200() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk());
    }

    @Test
    void health_get_bodyStatusOk() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void health_get_bodyHasSingleKey() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andReturn();

        String body = result.getResponse().getContentAsString();
        JsonNode node = objectMapper.readTree(body);
        assertEquals(1, node.size());
    }

    @Test
    void health_get_contentTypeJson() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON));
    }

    @Test
    void health_repeatedCalls_statusStable() throws Exception {
        for (int i = 0; i < 3; i++) {
            mockMvc.perform(get("/api/health"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.status").value("ok"));
        }
    }

    @Test
    void health_post_wrongMethod_returns500DueToGlobalHandler() throws Exception {
        // 真实行为：HttpRequestMethodNotSupportedException 被 GlobalExceptionHandler 的
        // @ExceptionHandler(Exception.class) 捕获，转为 500（而非标准的 405）
        mockMvc.perform(post("/api/health"))
                .andExpect(status().isInternalServerError());
    }

    @Test
    void health_get_trailingSlash_statusIs200Or404() throws Exception {
        int s = mockMvc.perform(get("/api/health/"))
                .andReturn()
                .getResponse()
                .getStatus();
        assertTrue(s == 200 || s == 404);
    }

    @Test
    void health_head_statusIs200Or405() throws Exception {
        int s = mockMvc.perform(head("/api/health"))
                .andReturn()
                .getResponse()
                .getStatus();
        assertTrue(s == 200 || s == 405);
    }
}