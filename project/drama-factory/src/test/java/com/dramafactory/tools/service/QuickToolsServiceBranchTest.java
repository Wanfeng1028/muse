package com.dramafactory.tools.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.service.AssetService;
import com.dramafactory.service.FfmpegService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class QuickToolsServiceBranchTest {

    @Mock AssetRepository assetRepository;
    @Mock AssetService assetService;
    @Mock FfmpegService ffmpegService;
    @Mock ShotRepository shotRepository;
    @Mock EpisodeRepository episodeRepository;
    @Mock ToolOpLogService toolOpLogService;
    @TempDir Path tempDir;

    QuickToolsService svc;

    @BeforeEach
    void init() {
        svc = new QuickToolsService(assetRepository, assetService, ffmpegService,
                shotRepository, episodeRepository, toolOpLogService, tempDir.toString());
    }

    @Test
    void batchTag_nullIds_throws() {
        assertThrows(IllegalArgumentException.class, () -> svc.batchTagAssets(null, "a", "merge"));
    }

    @Test
    void batchTag_modeNull_defaultsToMerge() {
        Asset a = new Asset();
        a.setId(1L);
        a.setTags("old");
        when(assetRepository.findAllById(any())).thenReturn(List.of(a));
        int result = svc.batchTagAssets(List.of(1L), "a", null);
        assertEquals(1, result);
        assertEquals("old,a", a.getTags());
        verify(toolOpLogService).log(eq("batchTagAssets"), eq("batch-tag"), anyString(), anyString(), eq(true));
    }

    @Test
    void batchTag_invalidMode_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.batchTagAssets(List.of(1L), "a", "xxx"));
        assertEquals("mode 只能为 merge 或 replace", ex.getMessage());
    }

    @Test
    void batchTag_mergeEmptyTags_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.batchTagAssets(List.of(1L), "  , ", "merge"));
        assertEquals("tags 不能为空", ex.getMessage());
    }

    @Test
    void batchTag_replaceEmptyTags_clearsTags() {
        Asset a = new Asset();
        a.setId(1L);
        a.setTags("old");
        when(assetRepository.findAllById(any())).thenReturn(List.of(a));
        svc.batchTagAssets(List.of(1L), null, "replace");
        assertNull(a.getTags());
    }

    @Test
    void batchRename_nullMap_throws() {
        assertThrows(IllegalArgumentException.class, () -> svc.batchRenameAssets(null));
    }

    @Test
    void batchRename_blankName_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.batchRenameAssets(Map.of(1L, "   ")));
        assertEquals("新文件名不能为空", ex.getMessage());
    }

    @Test
    void batchRename_tooLongName_throws() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 201; i++) {
            sb.append('a');
        }
        String name = sb.toString();
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.batchRenameAssets(Map.of(1L, name)));
        assertEquals("新文件名长度必须在 1~200 之间", ex.getMessage());
    }

    @Test
    void batchRename_notFound_throws() {
        when(assetRepository.findById(99L)).thenReturn(Optional.empty());
        assertThrows(ResourceNotFoundException.class,
                () -> svc.batchRenameAssets(Map.of(99L, "new.mp4")));
        verify(toolOpLogService).log(eq("batchRenameAssets"), eq("batch-rename"), anyString(), anyString(), eq(false));
    }

    @Test
    void convertVideo_nullFormat_defaultsMp4() throws Exception {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setType(AssetType.VIDEO);
        asset.setFilePath("assets/v.mp4");
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));
        doAnswer(inv -> {
            Path out = inv.getArgument(1);
            Files.createFile(out);
            return null;
        }).when(ffmpegService).convertVideo(any(Path.class), any(Path.class), anyString(), any());
        Asset created = new Asset();
        created.setId(7L);
        when(assetService.registerGenerated(anyString(), any(), anyString(), anyLong(), anyString(), any(), any()))
                .thenReturn(created);
        Asset result = svc.convertVideo(1L, null, null);
        assertEquals(7L, result.getId());
        verify(toolOpLogService).log(eq("convertVideo"), eq("video-convert"), anyString(), anyString(), eq(true));
    }

    @Test
    void convertVideo_invalidFormat_throws() {
        assertThrows(IllegalArgumentException.class, () -> svc.convertVideo(1L, "avi", null));
    }

    @Test
    void convertVideo_maxWidthTooSmall_throws() {
        assertThrows(IllegalArgumentException.class, () -> svc.convertVideo(1L, "mp4", 100));
        assertThrows(IllegalArgumentException.class, () -> svc.convertVideo(1L, "mp4", 5000));
    }

    @Test
    void convertVideo_assetNotFound_throws() {
        when(assetRepository.findById(1L)).thenReturn(Optional.empty());
        assertThrows(ResourceNotFoundException.class, () -> svc.convertVideo(1L, "mp4", null));
    }

    @Test
    void convertVideo_ffmpegFails_logsFailure() {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setType(AssetType.VIDEO);
        asset.setFilePath("assets/v.mp4");
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));
        doThrow(new RuntimeException("boom")).when(ffmpegService)
                .convertVideo(any(Path.class), any(Path.class), anyString(), any());
        assertThrows(RuntimeException.class, () -> svc.convertVideo(1L, "mp4", null));
        verify(toolOpLogService).log(eq("convertVideo"), eq("video-convert"), anyString(), anyString(), eq(false));
    }

    @Test
    void extractAudio_nullFormat_defaultsMp3() throws Exception {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setType(AssetType.VIDEO);
        asset.setFilePath("assets/v.mp4");
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));
        doAnswer(inv -> {
            Path out = inv.getArgument(1);
            Files.createFile(out);
            return null;
        }).when(ffmpegService).extractAudio(any(Path.class), any(Path.class), anyString());
        Asset created = new Asset();
        created.setId(9L);
        when(assetService.registerGenerated(anyString(), any(), anyString(), anyLong(), anyString(), any(), any()))
                .thenReturn(created);
        svc.extractAudio(1L, null);
        verify(assetService).registerGenerated(anyString(), eq(AssetType.AUDIO), eq("audio/mpeg"),
                anyLong(), eq("quick-tools"), any(), any());
    }

    @Test
    void extractAudio_invalidFormat_throws() {
        assertThrows(IllegalArgumentException.class, () -> svc.extractAudio(1L, "flac"));
    }

    @Test
    void exportShotCsv_nullFields_emptyCells() {
        Episode episode = org.mockito.Mockito.mock(Episode.class);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        Shot shot = org.mockito.Mockito.mock(Shot.class);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(shot));
        byte[] bytes = svc.exportShotCsv(1L);
        String csv = new String(bytes, StandardCharsets.UTF_8);
        assertTrue(csv.contains("镜号"));
        assertTrue(csv.contains(",,"));
    }

    @Test
    void exportShotCsv_escapeSpecialChars() {
        Episode episode = org.mockito.Mockito.mock(Episode.class);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        Shot shot = org.mockito.Mockito.mock(Shot.class);
        when(shot.getDescription()).thenReturn("a,b\"c");
        when(shot.getDialogue()).thenReturn("x\ny");
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(shot));
        byte[] bytes = svc.exportShotCsv(1L);
        String csv = new String(bytes, StandardCharsets.UTF_8);
        assertTrue(csv.contains("\"a,b\"\"c\""));
    }

    @Test
    void exportShotCsv_episodeNotFound_logsFailure() {
        when(episodeRepository.findById(1L)).thenReturn(Optional.empty());
        assertThrows(ResourceNotFoundException.class, () -> svc.exportShotCsv(1L));
        verify(toolOpLogService).log(eq("exportShotCsv"), eq("episode-shots-csv"), anyString(), anyString(), eq(false));
    }

    @Test
    void convertVideo_illegalPath_throws() {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setType(AssetType.VIDEO);
        asset.setFilePath("evil.mp4");
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.convertVideo(1L, "mp4", null));
        assertEquals("资产路径非法", ex.getMessage());
    }
}
