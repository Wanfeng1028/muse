package com.dramafactory.controller;

import com.dramafactory.service.SettingsService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import com.dramafactory.config.JwtVerifier;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = SettingsController.class)
class SettingsControllerTest {

    @MockBean
    private JwtVerifier jwtVerifier;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private SettingsService settingsService;

    @MockBean
    private com.dramafactory.service.video.VideoProviderRouter videoProviderRouter;

    @Test
    void getReturnsSchemaAndMaskedValues() throws Exception {
        when(settingsService.schema()).thenReturn(List.of(
                Map.of("key", "deepseek.api-key", "label", "DeepSeek API Key",
                        "type", "password", "secret", true, "restartRequired", false)));
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("deepseek.api-key", "****3456");
        when(settingsService.maskedView()).thenReturn(values);

        mockMvc.perform(get("/api/settings"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.schema[0].key").value("deepseek.api-key"))
                .andExpect(jsonPath("$.values['deepseek.api-key']").value("****3456"));
    }

    @Test
    void putInvalidKeyReturns400() throws Exception {
        when(settingsService.allowedKeys()).thenReturn(Set.of("deepseek.api-key"));

        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("not.allowed", "x");

        mockMvc.perform(put("/api/settings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(patch)))
                .andExpect(status().isBadRequest());

        verify(settingsService, never()).saveAll(any());
    }

    @Test
    void putSecretEmptyDoesNotOverride() throws Exception {
        when(settingsService.allowedKeys()).thenReturn(Set.of("deepseek.api-key", "drama.video.provider"));
        when(settingsService.maskedView()).thenReturn(new LinkedHashMap<>());

        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("deepseek.api-key", "");
        patch.put("drama.video.provider", "qwen");

        mockMvc.perform(put("/api/settings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(patch)))
                .andExpect(status().isOk());

        verify(settingsService).saveAll(org.mockito.ArgumentMatchers.argThat(m ->
                !m.containsKey("deepseek.api-key") && "qwen".equals(m.get("drama.video.provider"))));
    }

    @Test
    void effectiveProviderReturnsCurrent() throws Exception {
        mockMvc.perform(get("/api/settings/effective-provider"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.provider").value("mock"));
    }
}
