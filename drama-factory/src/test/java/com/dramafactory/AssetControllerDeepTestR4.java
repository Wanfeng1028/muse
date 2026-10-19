package com.dramafactory;

import com.dramafactory.controller.AssetController;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.service.AssetService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AssetControllerDeepTestR4 {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private AssetService assetService;

    private Asset mockAsset(Long id, String fileName, Long fileSize, String tags, LocalDateTime createdAt) {
        Asset asset = mock(Asset.class);
        when(asset.getId()).thenReturn(id);
        when(asset.getFileName()).thenReturn(fileName);
        when(asset.getFileSize()).thenReturn(fileSize);
        when(asset.getTags()).thenReturn(tags);
        when(asset.getCreatedAt()).thenReturn(createdAt);
        return asset;
    }

    @Test
    void upload_withTags_returnsDto() throws Exception {
        Asset asset = mockAsset(1L, "a.png", 3L, "夜景", null);
        when(assetService.upload(any(), eq("夜景"), isNull())).thenReturn(asset);

        MockMultipartFile file = new MockMultipartFile(
                "file", "a.png", "image/png", new byte[]{1, 2, 3});

        mockMvc.perform(multipart("/api/assets/upload")
                        .file(file)
                        .param("tags", "夜景"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.fileName").value("a.png"));

        verify(assetService).upload(any(), eq("夜景"), isNull());
    }

    @Test
    void upload_noFile_returns500DueToGlobalHandler() throws Exception {
        // 真实行为：缺失必填 multipart 文件抛 MissingServletRequestPartException，被
        // GlobalExceptionHandler 的 @ExceptionHandler(Exception.class) 捕获，转为 500（而非 400）
        mockMvc.perform(multipart("/api/assets/upload"))
                .andExpect(status().isInternalServerError());
    }

    @Test
    void upload_withRunId_passThrough() throws Exception {
        Asset asset = mockAsset(2L, "a.png", 3L, null, null);
        when(assetService.upload(any(), isNull(), eq(77L))).thenReturn(asset);

        MockMultipartFile file = new MockMultipartFile(
                "file", "a.png", "image/png", new byte[]{1, 2, 3});

        mockMvc.perform(multipart("/api/assets/upload")
                        .file(file)
                        .param("runId", "77"))
                .andExpect(status().isOk());

        verify(assetService).upload(any(), isNull(), eq(77L));
    }

    @Test
    void list_withTypeFilter_passThrough() throws Exception {
        when(assetService.list(isNull(), isNull(), eq("夜景"))).thenReturn(List.of());

        mockMvc.perform(get("/api/assets/").param("keyword", "夜景"))
                .andExpect(status().isOk());

        verify(assetService).list(isNull(), isNull(), eq("夜景"));
    }

    @Test
    void list_empty_returnsEmptyArray() throws Exception {
        when(assetService.list(any(), any(), any())).thenReturn(List.of());

        mockMvc.perform(get("/api/assets/"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void list_mapsDtoFields() throws Exception {
        Asset asset = mockAsset(5L, "b.mp4", 12345L, "t1", null);
        when(assetService.list(any(), any(), any())).thenReturn(List.of(asset));

        mockMvc.perform(get("/api/assets/"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].id").value(5))
                .andExpect(jsonPath("$[0].fileName").value("b.mp4"))
                .andExpect(jsonPath("$[0].fileSize").value(12345));
    }

    @Test
    void updateTags_nullBody_returns500DueToGlobalHandler() throws Exception {
        // 真实行为：缺失 @RequestBody 抛 HttpMessageNotReadableException，被 GlobalExceptionHandler 的
        // @ExceptionHandler(Exception.class) 捕获，转为 500（而非 200）
        mockMvc.perform(put("/api/assets/6/tags"))
                .andExpect(status().isInternalServerError());
    }

    @Test
    void updateTags_unknownId_returns404() throws Exception {
        when(assetService.tag(eq(99L), any()))
                .thenThrow(new ResourceNotFoundException("Asset", 99L));

        mockMvc.perform(put("/api/assets/99/tags")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"tags\":\"x\"}"))
                .andExpect(status().isNotFound());
    }

    @Test
    void reuse_episodeAndShot_passThrough() throws Exception {
        Asset asset = mockAsset(8L, "d.png", 1L, null, null);
        when(assetService.reuse(eq(8L), eq(1L), eq(2L))).thenReturn(asset);

        mockMvc.perform(post("/api/assets/8/reuse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"episodeId\":1,\"shotId\":2}"))
                .andExpect(status().isOk());

        verify(assetService).reuse(eq(8L), eq(1L), eq(2L));
    }

    @Test
    void reuse_serviceThrows_returns404() throws Exception {
        when(assetService.reuse(eq(8L), any(), any()))
                .thenThrow(new ResourceNotFoundException("Asset", 8L));

        mockMvc.perform(post("/api/assets/8/reuse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"episodeId\":1,\"shotId\":2}"))
                .andExpect(status().isNotFound());
    }

    @Test
    void delete_unknownId_returns404() throws Exception {
        doThrow(new ResourceNotFoundException("Asset", 55L))
                .when(assetService).delete(eq(55L));

        mockMvc.perform(delete("/api/assets/55"))
                .andExpect(status().isNotFound());
    }

    @Test
    void delete_valid_returns204() throws Exception {
        mockMvc.perform(delete("/api/assets/12"))
                .andExpect(status().isNoContent());

        verify(assetService).delete(eq(12L));
    }

    @Test
    void upload_serviceThrowsIllegalArgument_returns400() throws Exception {
        when(assetService.upload(any(), any(), any()))
                .thenThrow(new IllegalArgumentException("空文件"));

        MockMultipartFile file = new MockMultipartFile(
                "file", "a.png", "image/png", new byte[]{1, 2, 3});

        mockMvc.perform(multipart("/api/assets/upload").file(file))
                .andExpect(status().isBadRequest());
    }

    @Test
    void list_dtoHasCreatedAt() throws Exception {
        LocalDateTime createdAt = LocalDateTime.of(2024, 1, 2, 3, 4, 5);
        Asset asset = mockAsset(7L, "e.png", 1L, null, createdAt);
        when(assetService.list(any(), any(), any())).thenReturn(List.of(asset));

        mockMvc.perform(get("/api/assets/"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].createdAt").isNotEmpty());
    }
}