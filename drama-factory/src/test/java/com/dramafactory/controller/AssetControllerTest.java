package com.dramafactory.controller;

import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.service.AssetService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AssetController 单元测试（直接调用 controller 方法，避免依赖 WebMvcTest）。
 */
class AssetControllerTest {

    @TempDir
    Path tempDir;

    private AssetService assetService;
    private AssetController controller;

    @BeforeEach
    void setUp() {
        assetService = mock(AssetService.class);
        controller = new AssetController(assetService, tempDir.toString());
    }

    private Asset sampleAsset() {
        Asset a = new Asset();
        a.setId(1L);
        a.setType(AssetType.IMAGE);
        a.setSource(AssetSource.UPLOADED);
        a.setFileName("a.png");
        a.setFilePath("assets/image/a.png");
        a.setMimeType("image/png");
        a.setFileSize(1024L);
        a.setCreatedAt(LocalDateTime.now());
        return a;
    }

    @Test
    void list_returnsDtos() {
        when(assetService.list(isNull(), isNull(), isNull()))
                .thenReturn(List.of(sampleAsset()));

        List<AssetController.AssetDto> result = controller.list(null, null, null);

        assertEquals(1, result.size());
        assertEquals(1L, result.get(0).id());
        assertEquals(AssetType.IMAGE, result.get(0).type());
    }

    @Test
    void reuse_passesParametersThrough() {
        Asset updated = sampleAsset();
        updated.setEpisodeId(10L);
        updated.setShotId(20L);
        when(assetService.reuse(eq(1L), eq(10L), eq(20L))).thenReturn(updated);

        AssetController.AssetDto dto = controller.reuse(1L,
                new AssetController.ReuseRequest(10L, 20L));

        assertNotNull(dto);
        assertEquals(10L, dto.episodeId());
        assertEquals(20L, dto.shotId());
        verify(assetService).reuse(1L, 10L, 20L);
    }

    @Test
    void reuse_nullBody_usesNulls() {
        Asset updated = sampleAsset();
        when(assetService.reuse(eq(1L), isNull(), isNull())).thenReturn(updated);

        AssetController.AssetDto dto = controller.reuse(1L, null);

        assertNotNull(dto);
        assertNull(dto.episodeId());
        verify(assetService).reuse(1L, null, null);
    }

    @Test
    void delete_delegates() {
        controller.delete(5L);
        verify(assetService).delete(5L);
    }

    @Test
    void updateTags_passesTags() {
        Asset updated = sampleAsset();
        updated.setTags("x,y");
        when(assetService.tag(eq(1L), eq("x,y"))).thenReturn(updated);

        AssetController.AssetDto dto = controller.updateTags(1L,
                new AssetController.TagRequest("x,y"));

        assertEquals("x,y", dto.tags());

        ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
        verify(assetService).tag(eq(1L), captor.capture());
        assertEquals("x,y", captor.getValue());
    }

    @Test
    void upload_delegates() {
        when(assetService.upload(any(), any(), any())).thenReturn(sampleAsset());
        org.springframework.mock.web.MockMultipartFile file =
                new org.springframework.mock.web.MockMultipartFile("file", "a.png", "image/png", new byte[10]);

        AssetController.AssetDto dto = controller.upload(file, "t", 3L);

        assertNotNull(dto);
        verify(assetService).upload(eq(file), eq("t"), eq(3L));
    }
}
