package com.dramafactory.service;

import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.repository.AssetRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.springframework.mock.web.MockMultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AssetService 单元测试。
 */
class AssetServiceTest {

    @TempDir
    Path tempDir;

    private AssetRepository assetRepository;
    private AssetService assetService;

    @BeforeEach
    void setUp() {
        assetRepository = mock(AssetRepository.class);
        assetService = new AssetService(assetRepository, tempDir.toString());
        when(assetRepository.save(any(Asset.class))).thenAnswer(inv -> inv.getArgument(0));
    }

    @Test
    void upload_image_success() throws IOException {
        byte[] data = new byte[1024];
        MockMultipartFile file = new MockMultipartFile("file", "pic.png", "image/png", data);

        Asset asset = assetService.upload(file, "a,b", 100L);

        assertNotNull(asset);
        assertEquals(AssetType.IMAGE, asset.getType());
        assertEquals(AssetSource.UPLOADED, asset.getSource());
        assertEquals("pic.png", asset.getFileName());
        assertEquals("a,b", asset.getTags());
        assertEquals(100L, asset.getRunId());
        assertTrue(asset.getFilePath().startsWith("assets/image/"));

        Path stored = tempDir.resolve(asset.getFilePath());
        assertTrue(Files.exists(stored), "文件应真实落盘");
        assertEquals(1024L, Files.size(stored));
        verify(assetRepository, times(1)).save(any(Asset.class));
    }

    @Test
    void upload_invalidType_throws() {
        MockMultipartFile file = new MockMultipartFile("file", "a.txt", "text/plain", new byte[10]);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> assetService.upload(file, null, null));
        assertTrue(ex.getMessage().contains("不支持"));
    }

    @Test
    void upload_tooLarge_throws() {
        MockMultipartFile file = mock(MockMultipartFile.class);
        when(file.isEmpty()).thenReturn(false);
        when(file.getSize()).thenReturn(51L * 1024 * 1024);
        when(file.getContentType()).thenReturn("image/png");
        when(file.getOriginalFilename()).thenReturn("big.png");

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> assetService.upload(file, null, null));
        assertTrue(ex.getMessage().contains("大小限制"));
    }

    @Test
    void upload_empty_throws() {
        MockMultipartFile file = new MockMultipartFile("file", "x.png", "image/png", new byte[0]);
        assertThrows(IllegalArgumentException.class, () -> assetService.upload(file, null, null));
    }

    @Test
    void delete_removesFileAndRecord() throws IOException {
        Path stored = tempDir.resolve("assets/image/a.png");
        Files.createDirectories(stored.getParent());
        Files.writeString(stored, "x");

        Asset asset = new Asset();
        asset.setId(1L);
        asset.setFilePath("assets/image/a.png");
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));

        assetService.delete(1L);

        assertTrue(Files.notExists(stored), "文件应被删除");
        verify(assetRepository, times(1)).delete(asset);
    }

    @Test
    void delete_rejectsTraversalPath() {
        Asset asset = new Asset();
        asset.setId(2L);
        asset.setFilePath("../../../etc/passwd");
        when(assetRepository.findById(2L)).thenReturn(Optional.of(asset));

        assertThrows(IllegalArgumentException.class, () -> assetService.delete(2L));
    }

    @Test
    void tag_deduplicates() {
        Asset asset = new Asset();
        asset.setId(1L);
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));

        Asset updated = assetService.tag(1L, " a , b ,a,  c , ");

        assertEquals("a,b,c", updated.getTags());
    }

    @Test
    void tag_blank_returnsNull() {
        Asset asset = new Asset();
        asset.setId(1L);
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));

        Asset updated = assetService.tag(1L, "   ");

        assertNull(updated.getTags());
    }

    @Test
    void registerGenerated_marksSourceGenerated() {
        Asset asset = assetService.registerGenerated(
                "/api/byok/file/image/abc.png", AssetType.IMAGE,
                "image/png", 2048L, "openai", "a cat", 7L);

        assertEquals(AssetSource.GENERATED, asset.getSource());
        assertEquals(AssetType.IMAGE, asset.getType());
        assertEquals("abc.png", asset.getFileName());
        assertEquals(7L, asset.getRunId());
        assertEquals("openai", asset.getProvider());
        assertEquals("a cat", asset.getPrompt());
        assertTrue(asset.getFilePath().startsWith("assets/"));

        ArgumentCaptor<Asset> captor = ArgumentCaptor.forClass(Asset.class);
        verify(assetRepository).save(captor.capture());
        assertEquals(AssetSource.GENERATED, captor.getValue().getSource());
    }
}
