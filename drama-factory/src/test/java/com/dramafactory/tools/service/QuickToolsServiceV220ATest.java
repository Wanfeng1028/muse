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

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class QuickToolsServiceV220ATest {

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

    private QuickToolsService svc;

    @BeforeEach
    void init() {
        svc = new QuickToolsService(
                assetRepository,
                assetService,
                ffmpegService,
                shotRepository,
                episodeRepository,
                toolOpLogService,
                tempDir.toString());
    }

    private Asset videoAsset(Long id, String filePath) {
        Asset a = new Asset();
        a.setId(id);
        a.setType(AssetType.VIDEO);
        a.setFilePath(filePath);
        a.setFileName("orig.mp4");
        return a;
    }

    // ========== batchRenameAssets：3 个未覆盖分支 ==========
    // 分支：len < 1（空串 trim 后长度 0）—— 已有 blankName 覆盖 null 和 "   "，
    // 但 len<1 的 left 侧用纯空串单独覆盖
    @Test
    void batchRename_trimToEmpty_lenLessThanOne_throws() {
        Map<Long, String> renames = new HashMap<>();
        renames.put(1L, "\t\n ");
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.batchRenameAssets(renames));
        assertEquals("新文件名不能为空", ex.getMessage());
    }

    // 分支：rename 正常路径（非空、长度合法）下 saveAll 成功并返回 count
    @Test
    void batchRename_validName_successPath() {
        Map<Long, String> renames = new HashMap<>();
        renames.put(10L, "  newName.mp4  ");
        Asset asset = videoAsset(10L, "assets/a.mp4");
        when(assetRepository.findById(10L)).thenReturn(Optional.of(asset));
        when(assetRepository.saveAll(any())).thenReturn(new ArrayList<>(List.of(asset)));

        int count = svc.batchRenameAssets(renames);

        assertEquals(1, count);
        assertEquals("newName.mp4", asset.getFileName());
    }

    // 分支：name == null 的右侧短路后 len 计算不被执行——覆盖 null 元素走到 continue 之前的路径
    // （已有 blankName_throws 覆盖 name.trim().isEmpty()，此处补 name==null 分支单独用例）
    @Test
    void batchRename_nullValueName_throws() {
        Map<Long, String> renames = new HashMap<>();
        renames.put(1L, null);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.batchRenameAssets(renames));
        assertEquals("新文件名不能为空", ex.getMessage());
    }

    // ========== convertVideo：1 个未覆盖分支 ==========
    // 分支：maxWidth != null 且合法（144~3840 之间），走成功路径
    @Test
    void convertVideo_maxWidthValid_successPath() throws Exception {
        Asset asset = videoAsset(1L, "assets/v.mp4");
        when(assetRepository.findById(1L)).thenReturn(Optional.of(asset));
        // 让 out 文件真实存在以通过 Files.size
        Path outDir = tempDir.resolve("assets").resolve("tools");
        Files.createDirectories(outDir);

        // 由于 fileName 是随机 UUID，无法预知；用 Answer 在调用时创建文件
        doAnswer(inv -> {
            Path out = inv.getArgument(1);
            Files.createDirectories(out.getParent());
            Files.write(out, new byte[]{1, 2, 3, 4, 5});
            return null;
        }).when(ffmpegService).convertVideo(any(), any(), anyString(), anyInt());

        Asset created = new Asset();
        created.setId(99L);
        when(assetService.registerGenerated(anyString(), eq(AssetType.VIDEO), anyString(),
                any(Long.class), anyString(), any(), any())).thenReturn(created);

        Asset result = svc.convertVideo(1L, "mp4", 1280);

        assertNotNull(result);
        assertEquals(99L, result.getId());
    }

    // ========== extractAudio：5 个未覆盖分支 ==========
    // 分支1：format == null 走默认 "mp3"（已有 nullFormat_defaultsMp3 覆盖，跳过）
    // 分支2：format 合法 wav（已有 invalidFormat 覆盖非法，成功路径的 wav 未覆盖）
    @Test
    void extractAudio_wavFormat_successPath() throws Exception {
        Asset asset = videoAsset(2L, "assets/a.mp4");
        when(assetRepository.findById(2L)).thenReturn(Optional.of(asset));

        doAnswer(inv -> {
            Path out = inv.getArgument(1);
            Files.createDirectories(out.getParent());
            Files.write(out, new byte[]{9, 9, 9});
            return null;
        }).when(ffmpegService).extractAudio(any(), any(), anyString());

        Asset created = new Asset();
        created.setId(77L);
        when(assetService.registerGenerated(anyString(), eq(AssetType.AUDIO), anyString(),
                any(Long.class), anyString(), any(), any())).thenReturn(created);

        Asset result = svc.extractAudio(2L, "wav");

        assertNotNull(result);
        assertEquals(77L, result.getId());
    }

    // 分支3：mimeType 三元 —— wav 分支走 "audio/wav"
    @Test
    void extractAudio_wavFormat_mimeTypeAudioWav() throws Exception {
        Asset asset = videoAsset(3L, "assets/b.mp4");
        when(assetRepository.findById(3L)).thenReturn(Optional.of(asset));

        doAnswer(inv -> {
            Path out = inv.getArgument(1);
            Files.createDirectories(out.getParent());
            Files.write(out, new byte[]{1});
            return null;
        }).when(ffmpegService).extractAudio(any(), any(), anyString());

        Asset created = new Asset();
        created.setId(78L);
        when(assetService.registerGenerated(anyString(), eq(AssetType.AUDIO), eq("audio/wav"),
                any(Long.class), anyString(), any(), any())).thenReturn(created);

        Asset result = svc.extractAudio(3L, "wav");

        assertNotNull(result);
        assertEquals(78L, result.getId());
    }

    // 分支4：ext 三元 —— wav 分支走 ".wav"（通过捕获输出文件名后缀验证）
    @Test
    void extractAudio_wavFormat_outputExtWav() throws Exception {
        Asset asset = videoAsset(4L, "assets/c.mp4");
        when(assetRepository.findById(4L)).thenReturn(Optional.of(asset));

        List<Path> captured = new ArrayList<>();
        doAnswer(inv -> {
            Path out = inv.getArgument(1);
            captured.add(out);
            Files.createDirectories(out.getParent());
            Files.write(out, new byte[]{1, 2});
            return null;
        }).when(ffmpegService).extractAudio(any(), any(), anyString());

        Asset created = new Asset();
        created.setId(79L);
        when(assetService.registerGenerated(anyString(), eq(AssetType.AUDIO), anyString(),
                any(Long.class), anyString(), any(), any())).thenReturn(created);

        svc.extractAudio(4L, "wav");

        assertEquals(1, captured.size());
        assertTrue(captured.get(0).toString().endsWith(".wav"));
    }

    // 分支5：catch (IOException e) 读取输出文件大小失败 —— 让 out 文件不存在触发 Files.size 抛 IOException
    @Test
    void extractAudio_sizeReadFails_throws() {
        Asset asset = videoAsset(5L, "assets/d.mp4");
        when(assetRepository.findById(5L)).thenReturn(Optional.of(asset));

        // 不创建 out 文件，Files.size 会抛 NoSuchFileException（IOException 子类）
        doAnswer(inv -> null).when(ffmpegService).extractAudio(any(), any(), anyString());

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.extractAudio(5L, "mp3"));
        assertTrue(ex.getMessage().startsWith("读取输出文件大小失败"));
    }

    // ========== exportShotCsv：2 个未覆盖分支 ==========
    // 分支：s.getShotNo() != null（三元 true 分支）——已有 nullFields 覆盖 false 分支
    @Test
    void exportShotCsv_shotNoNotNull_usesValue() {
        Episode ep = new Episode();
        ep.setId(50L);
        when(episodeRepository.findById(50L)).thenReturn(Optional.of(ep));

        Shot s = new Shot();
        s.setShotNo(7);
        s.setShotSize(null);
        s.setCameraMove(null);
        s.setDescription(null);
        s.setDialogue(null);
        s.setDurationSeconds(null);
        s.setCreatedAt(null);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(50L)).thenReturn(List.of(s));

        byte[] out = svc.exportShotCsv(50L);

        assertNotNull(out);
        String text = new String(out, java.nio.charset.StandardCharsets.UTF_8);
        assertTrue(text.contains("7"));
    }

    // 分支：s.getDurationSeconds() != null（三元 true 分支）
    @Test
    void exportShotCsv_durationNotNull_usesValue() {
        Episode ep = new Episode();
        ep.setId(51L);
        when(episodeRepository.findById(51L)).thenReturn(Optional.of(ep));

        Shot s = new Shot();
        s.setShotNo(1);
        s.setShotSize(null);
        s.setCameraMove(null);
        s.setDescription(null);
        s.setDialogue(null);
        s.setDurationSeconds(25);
        s.setCreatedAt(null);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(51L)).thenReturn(List.of(s));

        byte[] out = svc.exportShotCsv(51L);

        assertNotNull(out);
        String text = new String(out, java.nio.charset.StandardCharsets.UTF_8);
        assertTrue(text.contains("25"));
    }

    // ========== resolveStoragePath：2 个未覆盖分支（经 convertVideo 间接触达） ==========
    // 分支1：filePath == null 走 !filePath.startsWith("assets/") 抛异常（filePath==null 左侧短路）
    @Test
    void convertVideo_filePathNull_throws() {
        Asset asset = new Asset();
        asset.setId(60L);
        asset.setType(AssetType.VIDEO);
        asset.setFilePath(null);
        when(assetRepository.findById(60L)).thenReturn(Optional.of(asset));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.convertVideo(60L, "mp4", null));
        assertEquals("资产路径非法", ex.getMessage());
    }

    // 分支2：filePath 不以 "assets/" 开头，走 startsWith false 抛异常
    @Test
    void convertVideo_filePathNotAssetsPrefix_throws() {
        Asset asset = videoAsset(61L, "other/a.mp4");
        when(assetRepository.findById(61L)).thenReturn(Optional.of(asset));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.convertVideo(61L, "mp4", null));
        assertEquals("资产路径非法", ex.getMessage());
    }

    // ========== splitTags：1 个未覆盖分支（经 batchTagAssets 间接触达） ==========
    // 分支：splitTags 中 v.isEmpty() 为 true 时跳过（已有 replaceEmptyTags 覆盖归一化路径，
    // 此处用含空元素的资产 tags 走 merge 路径的 splitTags(a.getTags()) 的 continue 臂）
    @Test
    void batchTag_mergeWithEmptyAssetTagsSplit_skipsEmpty() {
        Asset asset = new Asset();
        asset.setId(70L);
        asset.setTags("a,,b");
        when(assetRepository.findAllById(List.of(70L))).thenReturn(List.of(asset));
        when(assetRepository.saveAll(any())).thenReturn(List.of(asset));

        int count = svc.batchTagAssets(List.of(70L), "c", "merge");

        assertEquals(1, count);
        assertEquals("a,b,c", asset.getTags());
    }

    // ========== csvEscape：2 个未覆盖分支（经 exportShotCsv 间接触达） ==========
    // 分支1：value 含 "\n"（换行）触发 needQuote true 且走替换分支
    @Test
    void exportShotCsv_newlineInField_quoted() {
        Episode ep = new Episode();
        ep.setId(80L);
        when(episodeRepository.findById(80L)).thenReturn(Optional.of(ep));

        Shot s = new Shot();
        s.setShotNo(1);
        s.setShotSize(null);
        s.setCameraMove(null);
        s.setDescription("line1\nline2");
        s.setDialogue(null);
        s.setDurationSeconds(null);
        s.setCreatedAt(null);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(80L)).thenReturn(List.of(s));

        byte[] out = svc.exportShotCsv(80L);

        String text = new String(out, java.nio.charset.StandardCharsets.UTF_8);
        assertTrue(text.contains("\"line1\nline2\""));
    }

    // 分支2：value 含 "\r"（回车）触发 needQuote true
    @Test
    void exportShotCsv_carriageReturnInField_quoted() {
        Episode ep = new Episode();
        ep.setId(81L);
        when(episodeRepository.findById(81L)).thenReturn(Optional.of(ep));

        Shot s = new Shot();
        s.setShotNo(1);
        s.setShotSize(null);
        s.setCameraMove(null);
        s.setDescription(null);
        s.setDialogue("car\rreturn");
        s.setDurationSeconds(null);
        s.setCreatedAt(null);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(81L)).thenReturn(List.of(s));

        byte[] out = svc.exportShotCsv(81L);

        String text = new String(out, java.nio.charset.StandardCharsets.UTF_8);
        assertTrue(text.contains("\"car\rreturn\""));
    }
}
