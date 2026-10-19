package com.dramafactory.pipeline;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.greaterThan;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * PipelineTemplateController 深度测试，使用 MockMvc 走完整 Spring MVC 栈。
 * 使用默认测试 H2 配置，校验模板列表、单模板详情及未知模板 404。
 */
@SpringBootTest
@AutoConfigureMockMvc
class PipelineTemplateControllerDeepTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void listTemplates_returns200WithThreeTemplates() throws Exception {
        mockMvc.perform(get("/api/pipeline-templates"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(3)))
                .andExpect(jsonPath("$[*].name").value(org.hamcrest.Matchers.hasItem("cinematic")));
    }

    @Test
    void getTemplate_cinematic_returnsFullTemplate() throws Exception {
        mockMvc.perform(get("/api/pipeline-templates/cinematic"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("cinematic"))
                .andExpect(jsonPath("$.stages").isArray())
                .andExpect(jsonPath("$.stages", hasSize(greaterThan(0))));
    }

    @Test
    void getTemplate_unknownName_returns404() throws Exception {
        mockMvc.perform(get("/api/pipeline-templates/no-such-template"))
                .andExpect(status().isNotFound());
    }
}
