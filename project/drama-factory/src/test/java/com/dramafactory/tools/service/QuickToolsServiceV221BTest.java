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
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class QuickToolsServiceV221BTest {

    @Mock
    private AssetRepository assetRepository;
    @Mock
    private AssetService assetService;
    @Mock
    private FfmpegService ffmpegService;
    @Mock
    private ShotRepository shotRepository;
    @Mock
    private EpisodeRepository episodeRepository;
    @Mock
    private ToolOpLogService toolOpLogService;

    @TempDir
    Path tempDir;

    private QuickToolsService service;

    @BeforeEach
    void setUp() {
        service = new QuickToolsService(
                assetRepository,
                assetService,
                ffmpegService,
                shotRepository,
                episodeRepository,
                toolOpLogService,
                tempDir.toString());
    }

    // ---- 1. L113 batchRenameAssets: renames.isEmpty() 臂 ----
    @Test
    void batchRenameAssets_emptyMap_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.batchRenameAssets(Map.of()));
        assertEquals("renames 不能为空", ex.getMessage());
    }

    // ---- 2. L122 batchRenameAssets: len > 200 抛异常臂 ----
    @Test
    void batchRenameAssets_nameTooLong_throws() {
        String tooLong = "a".repeat(201);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.batchRenameAssets(Map.of(1L, tooLong)));
        assertEquals("新文件名长度必须在 1~200 之间", ex.getMessage());
    }

    // ---- 4. L212 extractAudio: type != VIDEO 抛异常臂 ----
    @Test
    void extractAudio_nonVideoAsset_throws() {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setType(AssetType.AUDIO);
        asset.setFilePath("assets/a.mp4");
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.extractAudio(1L, "mp3"));
        assertEquals("只有视频资产可以转换", ex.getMessage());
    }

    // ---- 6. L266 exportShotCsv: getShotNo() != null 臂（shotNo=3，其余 null） ----
    @Test
    void exportShotCsv_shotNoPresent_rendersShotNo() {
        Episode episode = new Episode();
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));

        Shot shot = new Shot();
        shot.setShotNo(3);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(shot));

        byte[] bytes = service.exportShotCsv(1L);
        String csv = new String(bytes, StandardCharsets.UTF_8);

        // 首字符为 UTF-8 BOM
        assertEquals('\uFEFF', csv.charAt(0));
        // 数据行首列为 shotNo=3（其余列均为空）
        assertTrue(csv.contains("\uFEFF\u955C\u53F7"), "应包含表头（BOM + 镜号）");
        assertTrue(csv.contains("\r\n3,"), "数据行应以 3 开头（shotNo 非空臂）");
    }

    // ---- 7. L290 resolveStoragePath: 路径越界抛异常臂 ----
    @Test
    void convertVideo_pathTraversal_throws() {
        Asset asset = new Asset();
        asset.setId(1L);
        asset.setType(AssetType.VIDEO);
        asset.setFilePath("assets/../../evil.mp4");
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.convertVideo(1L, "mp4", null));
        assertEquals("资产路径越界", ex.getMessage());
    }
}
