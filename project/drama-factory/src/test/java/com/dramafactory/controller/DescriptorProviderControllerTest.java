package com.dramafactory.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:descriptorprovider;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"})
class DescriptorProviderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldReturnOkStatus() throws Exception {
        mockMvc.perform(get("/api/descriptor-providers"))
                .andExpect(status().isOk());
    }

    @Test
    void shouldReturnNonEmptyArray() throws Exception {
        mockMvc.perform(get("/api/descriptor-providers"))
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$[*]").exists());
    }

    @Test
    void shouldContainToonflowApimartProvider() throws Exception {
        mockMvc.perform(get("/api/descriptor-providers"))
                .andExpect(jsonPath("$[?(@.id == 'toonflow-apimart')]").exists());
    }

    @Test
    void shouldHaveMaxPromptChars500ForSeedance2() throws Exception {
        mockMvc.perform(get("/api/descriptor-providers"))
                .andExpect(jsonPath("$[?(@.id == 'toonflow-apimart')].models[?(@.id == 'seedance-2.0')].constraints.maxPromptChars").value(500));
    }

    @Test
    void shouldHaveMaxReferenceImages9ForMiniMaxH3() throws Exception {
        mockMvc.perform(get("/api/descriptor-providers"))
                .andExpect(jsonPath("$[?(@.id == 'toonflow-metaso')].models[?(@.id == 'MiniMax-H3')].constraints.maxReferenceImages").value(9));
    }

    @Test
    void shouldReturnJsonContentType() throws Exception {
        mockMvc.perform(get("/api/descriptor-providers"))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON));
    }
}
