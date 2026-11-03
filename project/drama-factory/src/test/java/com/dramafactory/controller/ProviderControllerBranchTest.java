package com.dramafactory.controller;

import com.dramafactory.config.JwtVerifier;
import com.dramafactory.service.PresetService;
import com.dramafactory.service.ProviderService;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProviderController.class)
class ProviderControllerBranchTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private JwtVerifier jwtVerifier;

    @MockBean
    private ProviderService providerService;

    @MockBean
    private PresetService presetService;

    private ProviderService.ProviderDto dto(String name) {
        return new ProviderService.ProviderDto(1L, name, "VIDEO", null, "", null, true, List.of());
    }

    private ProviderService.ModelDto modelDto(String displayName) {
        return new ProviderService.ModelDto(2L, displayName, "m-1", "1080p", null, 1, true);
    }

    // L93 m4c0: createProvider name==null → 400
    @Test
    void branch_createProvider_nameNull_returns400() throws Exception {
        mockMvc.perform(post("/api/providers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":null}"))
                .andExpect(status().isBadRequest());
    }

    // L93 m4c0: createProvider name 全空白 → 400
    @Test
    void branch_createProvider_nameBlank_returns400() throws Exception {
        mockMvc.perform(post("/api/providers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\" \"}"))
                .andExpect(status().isBadRequest());
    }

    // L93 m4c0 (else 分支) + L96-98: createProvider name 合法 → 200，返回 dto
    @Test
    void branch_createProvider_nameOk_returns200() throws Exception {
        when(providerService.createProvider(any(), any(), any(), any(), any())).thenReturn(dto("ok"));

        mockMvc.perform(post("/api/providers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"ok\",\"module\":\"VIDEO\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("ok"));
    }

    // L105 m4c0: updateProvider name 空串 → 400
    @Test
    void branch_updateProvider_nameEmpty_returns400() throws Exception {
        mockMvc.perform(put("/api/providers/1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest());
    }

    // L105 m4c0 (else 分支) + L108-110: updateProvider name 合法 → 200
    @Test
    void branch_updateProvider_nameOk_returns200() throws Exception {
        when(providerService.updateProvider(any(), any(), any(), any(), any(), any(), any()))
                .thenReturn(dto("新"));

        mockMvc.perform(put("/api/providers/1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"新\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("新"));
    }

    // L126 m4c0: addModel displayName 空串 → 400
    @Test
    void branch_addModel_displayNameEmpty_returns400() throws Exception {
        mockMvc.perform(post("/api/providers/1/models")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"displayName\":\"\"}"))
                .andExpect(status().isBadRequest());
    }

    // L126 m4c0 (else 分支) + L129-131: addModel displayName 合法 → 200
    @Test
    void branch_addModel_displayNameOk_returns200() throws Exception {
        when(providerService.addModel(any(), any(), any(), any(), any(), any()))
                .thenReturn(modelDto("m"));

        mockMvc.perform(post("/api/providers/1/models")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"displayName\":\"m\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("m"));
    }

    // L139 m4c0: updateModel displayName 全空白 → 400
    @Test
    void branch_updateModel_displayNameBlank_returns400() throws Exception {
        mockMvc.perform(put("/api/providers/1/models/2")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"displayName\":\" \"}"))
                .andExpect(status().isBadRequest());
    }

    // L139 m4c0 (else 分支) + L143-145: updateModel displayName 合法 → 200
    @Test
    void branch_updateModel_displayNameOk_returns200() throws Exception {
        when(providerService.updateModel(any(), any(), any(), any(), any(), any(), any(), any()))
                .thenReturn(modelDto("m2"));

        mockMvc.perform(put("/api/providers/1/models/2")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"displayName\":\"m2\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("m2"));
    }

    // L173 m4c0: createFromPreset presetId 空串 → 400
    @Test
    void branch_createFromPreset_presetIdEmpty_returns400() throws Exception {
        mockMvc.perform(post("/api/providers/from-preset")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"presetId\":\"\",\"apiKey\":\"k\"}"))
                .andExpect(status().isBadRequest());
    }

    // L173-174 m4c0: createFromPreset apiKey 空串 → 400
    @Test
    void branch_createFromPreset_apiKeyEmpty_returns400() throws Exception {
        mockMvc.perform(post("/api/providers/from-preset")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"presetId\":\"p1\",\"apiKey\":\"\"}"))
                .andExpect(status().isBadRequest());
    }

    // L173-174 m4c0 (else 分支) + L177: createFromPreset 两者合法 → 200，且 presetId 被 trim
    @Test
    void branch_createFromPreset_ok_trimsPresetIdAndReturns200() throws Exception {
        when(presetService.createFromPreset(any(), any())).thenReturn(dto("fromPreset"));

        mockMvc.perform(post("/api/providers/from-preset")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"presetId\":\"  p1  \",\"apiKey\":\"k\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("fromPreset"));

        ArgumentCaptor<String> presetCaptor = ArgumentCaptor.forClass(String.class);
        verify(presetService).createFromPreset(presetCaptor.capture(), eq("k"));
        assertThat(presetCaptor.getValue()).isEqualTo("p1");
    }
}
