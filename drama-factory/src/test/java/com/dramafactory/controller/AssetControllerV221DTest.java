package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetType;
import com.dramafactory.service.AssetService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.core.io.Resource;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AssetControllerV221DTest {

    private AssetService assetService;

    private AssetController controller;

    @TempDir
    Path tempDir;

    @BeforeEach
    void setUp() {
        assetService = mock(AssetService.class);
        controller = new AssetController(assetService, tempDir.toString());
    }

    // ---------- L71: updateTags body == null ----------

    @Test
    void updateTags_nullBody_passesNullTags() {
        when(assetService.tag(eq(1L), isNull())).thenReturn(new Asset());

        AssetController.AssetDto result = controller.updateTags(1L, null);

        assertNotNull(result);
    }

    // ---------- L94: filter lambda 分支 ----------

    @Test
    void file_filterIdNull_throwsNotFound() throws Exception {
        Files.createDirectories(tempDir.resolve("assets"));
        Files.writeString(tempDir.resolve("assets/f.txt"), "hello");

        Asset asset = new Asset();
        asset.setFilePath("assets/f.txt");

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        assertThrows(ResourceNotFoundException.class, () -> controller.file(1L));
    }

    @Test
    void file_filterIdMismatch_throwsNotFound() throws Exception {
        Files.createDirectories(tempDir.resolve("assets"));
        Files.writeString(tempDir.resolve("assets/f.txt"), "hello");

        Asset asset = new Asset();
        asset.setId(2L);
        asset.setFilePath("assets/f.txt");

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        assertThrows(ResourceNotFoundException.class, () -> controller.file(1L));
    }

    @Test
    void file_filterBothConditionsTrue_returnsOk() throws Exception {
        Files.createDirectories(tempDir.resolve("assets"));
        Files.writeString(tempDir.resolve("assets/f.txt"), "hello");

        Asset asset = new Asset();
        asset.setId(1L);
        asset.setFilePath("assets/f.txt");
        asset.setFileName("f.txt");

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        ResponseEntity<Resource> response = controller.file(1L);

        assertEquals(200, response.getStatusCode().value());
        assertNotNull(response.getBody());
    }

    // ---------- L99: filePath null / 非法前缀 ----------

    @Test
    void file_filePathNull_throwsIllegalArgument() {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setFilePath(null);

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> controller.file(1L));
        assertEquals("非法的资产文件路径", ex.getMessage());
    }

    @Test
    void file_filePathBadPrefix_throwsIllegalArgument() {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setFilePath("evil.txt");

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> controller.file(1L));
        assertEquals("非法的资产文件路径", ex.getMessage());
    }

    // ---------- L104: normalize 越界 / 文件不存在 ----------

    @Test
    void file_pathEscapesBase_throwsNotFound() {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setFilePath("assets/../../evil.txt");

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        assertThrows(ResourceNotFoundException.class, () -> controller.file(1L));
    }

    @Test
    void file_missingFile_throwsNotFound() {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setFilePath("assets/missing.txt");

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        assertThrows(ResourceNotFoundException.class, () -> controller.file(1L));
    }

    // ---------- L109: mimeType != null / == null ----------

    @Test
    void file_mimeTypeValid_usesParsedContentType() throws Exception {
        Files.createDirectories(tempDir.resolve("assets"));
        Files.writeString(tempDir.resolve("assets/f.txt"), "hello");

        Asset asset = new Asset();
        asset.setId(1L);
        asset.setFilePath("assets/f.txt");
        asset.setFileName("f.txt");
        asset.setMimeType("text/plain");

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        ResponseEntity<Resource> response = controller.file(1L);

        assertEquals(MediaType.TEXT_PLAIN, response.getHeaders().getContentType());
    }

    @Test
    void file_mimeTypeNull_usesOctetStream() throws Exception {
        Files.createDirectories(tempDir.resolve("assets"));
        Files.writeString(tempDir.resolve("assets/f.txt"), "hello");

        Asset asset = new Asset();
        asset.setId(1L);
        asset.setFilePath("assets/f.txt");
        asset.setFileName("f.txt");
        asset.setMimeType(null);

        when(assetService.list(isNull(), isNull(), isNull())).thenReturn(List.of(asset));

        ResponseEntity<Resource> response = controller.file(1L);

        assertEquals(MediaType.APPLICATION_OCTET_STREAM,
                response.getHeaders().getContentType());
    }
}
