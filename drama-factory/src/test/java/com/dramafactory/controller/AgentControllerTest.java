package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.model.PromptTemplate;
import com.dramafactory.model.AgentType;
import com.dramafactory.service.PromptTemplateService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import com.dramafactory.config.JwtVerifier;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * AgentController 测试。
 *
 * <p>注意：不 mock Environment（mock 会导致容器内 ValidationAutoConfiguration 等
 * 基础设施读取属性时 NPE）；直接使用测试容器中的真实 Environment，取默认值断言。</p>
 */
@WebMvcTest(AgentController.class)
class AgentControllerTest {

    @MockBean
    private JwtVerifier jwtVerifier;

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private PromptTemplateService promptTemplateService;

    @Test
    void listReturnsFiveAgents() throws Exception {
        PromptTemplate template = new PromptTemplate();
        template.setName("tpl");
        when(promptTemplateService.getByAgent(any(AgentType.class))).thenReturn(template);

        mockMvc.perform(get("/api/agents"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(5));
    }

    @Test
    void putInvalidTypeReturns400() throws Exception {
        mockMvc.perform(put("/api/agents/unknown/template")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"hello\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void putBlankContentReturns400() throws Exception {
        mockMvc.perform(put("/api/agents/script/template")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"  \"}"))
                .andExpect(status().isBadRequest());
    }
}
