package com.dramafactory.service;

/*
 * 覆盖说明（行号 -> 测试方法）：
 * 第66行  if (file == null || file.isEmpty()) 的 file==null 臂 -> upload_nullFile_throws
 * 第80行  if (originalName == null || originalName.isBlank()) 的 null 臂 -> upload_nullOriginalName_fallsBackToFile
 * 第80行  if (originalName == null || originalName.isBlank()) 的 isBlank 臂 -> upload_blankOriginalName_fallsBackToFile
 * 第116行 list() 的 keyword==null 臂 -> list_nullKeyword_passesNull
 * 第116行 list() 的 keyword 为空白臂 -> list_blankKeyword_passesNull
 * 第116行 list() 的 keyword trim 臂 -> list_keywordTrimmed
 * 第140行 if (filePath == null || !filePath.startsWith(ASSET_PREFIX)) 的 filePath==null 臂 -> delete_nullFilePath_throws
 * 第179行 if (filePath == null || filePath.isBlank()) 的 filePath==null 臂 -> registerGenerated_nullFilePath_throws
 * 第179行 if (filePath == null || filePath.isBlank()) 的 isBlank 臂 -> registerGenerated_blankFilePath_throws
 * 第206行 if (mimeType == null || mimeType.isBlank()) 的 mimeType==null 臂 -> upload_nullContentType_throws
 * 第206行 if (mimeType == null || mimeType.isBlank()) 的 isBlank 臂 -> upload_blankContentType_throws
 * 第216行 if (m.startsWith("video/")) 的 true 臂 -> upload_videoType_returnsVideo
 * 第229行 if (!resolved.startsWith(base)) 的 true 臂 -> registerGenerated_traversalPath_throws
 * 第237行 if (tags == null || tags.isBlank()) 的 tags==null 臂 -> upload_nullTags_returnsNullTags
 * 第247行 return set.isEmpty() ? null : String.join(",", set) 的空集臂 -> tag_allBlankTags_returnsNull
 * 第253行 if (idx < 0 || idx == fileName.length() - 1) 的 idx<0 臂 -> upload_noExtension_filePathHasNoExt
 * 第253行 if (idx < 0 || idx == fileName.length() - 1) 的末尾点臂 -> upload_trailingDot_filePathHasNoExt
 *
 * 诚实跳过清单：
 * - 第262行 lastSegment 的 idx<0 臂：registerGenerated 恒会给 relative 加上 "assets/" 前缀，
 *   因此 relative 必含 '/'，该分支经 public API 不可达，不写测试。
 */

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.repository.AssetRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.springframework.mock.web.MockMultipartFile;

import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AssetServiceBranchTest {

    @TempDir
    Path tempDir;

    private AssetService newService(AssetRepository repo) {
        return new AssetService(repo, tempDir.toString());
    }

    private AssetRepository repoEchoingSave() {
        AssetRepository repo = mock(AssetRepository.class);
        when(repo.save(any(Asset.class))).thenAnswer(inv -> inv.getArgument(0));
        return repo;
    }

    @Test
    void upload_nullFile_throws() {
        AssetRepository repo = mock(AssetRepository.class);
        AssetService service = newService(repo);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.upload(null, null, null));
        assertTrue(ex.getMessage().contains("上传文件不能为空"));
    }

    @Test
    void upload_nullOriginalName_fallsBackToFile() {
        AssetRepository repo = repoEchoingSave();
        AssetService service = newService(repo);
        MockMultipartFile file = new MockMultipartFile("f", null, "image/png", "x".getBytes());
        Asset result = service.upload(file, null, null);
        assertEquals("file", result.getFileName());
    }

    @Test
    void upload_blankOriginalName_fallsBackToFile() {
        AssetRepository repo = repoEchoingSave();
        AssetService service = newService(repo);
        MockMultipartFile file = new MockMultipartFile("f", " ", "image/png", "x".getBytes());
        Asset result = service.upload(file, null, null);
        assertEquals("file", result.getFileName());
    }

    @Test
    void list_nullKeyword_passesNull() {
        AssetRepository repo = mock(AssetRepository.class);
        when(repo.search(any(), any(), any())).thenReturn(List.of());
        AssetService service = newService(repo);
        service.list(null, null, null);
        verify(repo).search(eq(null), eq(null), eq(null));
    }

    @Test
    void list_blankKeyword_passesNull() {
        AssetRepository repo = mock(AssetRepository.class);
        when(repo.search(any(), any(), any())).thenReturn(List.of());
        AssetService service = newService(repo);
        service.list(null, null, " ");
        verify(repo).search(eq(null), eq(null), eq(null));
    }

    @Test
    void list_keywordTrimmed() {
        AssetRepository repo = mock(AssetRepository.class);
        when(repo.search(any(), any(), any())).thenReturn(List.of());
        AssetService service = newService(repo);
        service.list(AssetType.IMAGE, null, " 猫 ");
        verify(repo).search(eq(AssetType.IMAGE), eq(null), eq("猫"));
    }

    @Test
    void delete_nullFilePath_throws() {
        AssetRepository repo = mock(AssetRepository.class);
        Asset asset = new Asset();
        asset.setFilePath(null);
        when(repo.findById(1L)).thenReturn(Optional.of(asset));
        AssetService service = newService(repo);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.delete(1L));
        assertTrue(ex.getMessage().contains("非法的资产文件路径"));
    }

    @Test
    void registerGenerated_nullFilePath_throws() {
        AssetRepository repo = mock(AssetRepository.class);
        AssetService service = newService(repo);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.registerGenerated(null, AssetType.IMAGE, "image/png", 1L, "p", "prompt", null));
        assertTrue(ex.getMessage().contains("生成资产的 filePath 不能为空"));
    }

    @Test
    void registerGenerated_blankFilePath_throws() {
        AssetRepository repo = mock(AssetRepository.class);
        AssetService service = newService(repo);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.registerGenerated(" ", AssetType.IMAGE, "image/png", 1L, "p", "prompt", null));
        assertTrue(ex.getMessage().contains("生成资产的 filePath 不能为空"));
    }

    @Test
    void upload_nullContentType_throws() {
        AssetRepository repo = mock(AssetRepository.class);
        AssetService service = newService(repo);
        MockMultipartFile file = new MockMultipartFile("f", "a.png", null, "x".getBytes());
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.upload(file, null, null));
        assertTrue(ex.getMessage().contains("不支持的文件类型"));
    }

    @Test
    void upload_blankContentType_throws() {
        AssetRepository repo = mock(AssetRepository.class);
        AssetService service = newService(repo);
        MockMultipartFile file = new MockMultipartFile("f", "a.png", " ", "x".getBytes());
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.upload(file, null, null));
        assertTrue(ex.getMessage().contains("不支持的文件类型"));
    }

    @Test
    void upload_videoType_returnsVideo() {
        AssetRepository repo = repoEchoingSave();
        AssetService service = newService(repo);
        MockMultipartFile file = new MockMultipartFile("f", "v.mp4", "video/mp4", "x".getBytes());
        Asset result = service.upload(file, null, null);
        assertEquals(AssetType.VIDEO, result.getType());
    }

    @Test
    void delete_traversalInsideAssetsPrefix_throws() {
        // 第 229 行 resolveSafePath 的 !resolved.startsWith(base) 真臂：
        // "assets/../../evil.png" 能过第 140 行的 startsWith("assets/") 检查，
        // 但 normalize 后越界到 storageDir 之外，被 resolveSafePath 拦截。
        // （注意 registerGenerated 不调 resolveSafePath，走不到这里，只能经 delete 触发。）
        AssetRepository repo = mock(AssetRepository.class);
        Asset asset = new Asset();
        asset.setFilePath("assets/../../evil.png");
        when(repo.findById(9L)).thenReturn(Optional.of(asset));
        AssetService service = newService(repo);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.delete(9L));
        assertTrue(ex.getMessage().contains("检测到非法路径穿越"));
    }

    @Test
    void upload_nullTags_returnsNullTags() {
        AssetRepository repo = repoEchoingSave();
        AssetService service = newService(repo);
        MockMultipartFile file = new MockMultipartFile("f", "a.png", "image/png", "x".getBytes());
        Asset result = service.upload(file, null, null);
        assertNull(result.getTags());
    }

    @Test
    void tag_allBlankTags_returnsNull() {
        AssetRepository repo = mock(AssetRepository.class);
        Asset asset = new Asset();
        when(repo.findById(1L)).thenReturn(Optional.of(asset));
        when(repo.save(any(Asset.class))).thenAnswer(inv -> inv.getArgument(0));
        AssetService service = newService(repo);
        Asset result = service.tag(1L, ",,,");
        assertNull(result.getTags());
    }

    @Test
    void upload_noExtension_filePathHasNoExt() {
        AssetRepository repo = repoEchoingSave();
        AssetService service = newService(repo);
        MockMultipartFile file = new MockMultipartFile("f", "noext", "image/png", "x".getBytes());
        service.upload(file, null, null);
        ArgumentCaptor<Asset> captor = ArgumentCaptor.forClass(Asset.class);
        verify(repo).save(captor.capture());
        String filePath = captor.getValue().getFilePath();
        assertTrue(filePath.startsWith("assets/image/"));
        String last = filePath.substring(filePath.lastIndexOf('/') + 1);
        assertFalse(last.contains("."));
    }

    @Test
    void upload_trailingDot_filePathHasNoExt() {
        AssetRepository repo = repoEchoingSave();
        AssetService service = newService(repo);
        MockMultipartFile file = new MockMultipartFile("f", "file.", "image/png", "x".getBytes());
        service.upload(file, null, null);
        ArgumentCaptor<Asset> captor = ArgumentCaptor.forClass(Asset.class);
        verify(repo).save(captor.capture());
        String filePath = captor.getValue().getFilePath();
        assertTrue(filePath.startsWith("assets/image/"));
        String last = filePath.substring(filePath.lastIndexOf('/') + 1);
        assertFalse(last.contains("."));
    }
}
