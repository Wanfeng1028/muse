package com.dramafactory.service;

// 本批跳过的不可达分支（已核验，不硬凑测试）：
// - L453 render clips.isEmpty()：空 sections 的 Timeline 经 fromJson（"时间轴为空"）/align（"作词结果为空"）/
//   buildInstrumentalTimeline（totalMs<=0 抛错）都构造不出来，public 路径不可达。
// - L541 findStep getSeqNo()!=null 的 false 半支：AgentStep.SEQ_NO 列 NOT NULL，null seqNo 存不进 DB。
// - L468/L587/L608/L630 render 字幕过滤/writeSrt/muxAudio 分支：需走完真实 ffmpeg 渲染链路，mock 下断言脆弱，跳过。
// - L570 resolveLocalAudio filePath==null 分支：Asset.FILE_PATH 列 NOT NULL，null filePath 存不进 DB，不可达
//   （filePath 含 ".." 的半支由既有测试 resolveLocalAudio_pathTraversal 覆盖）。

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.MvSong;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.MvSongRepository;
import com.dramafactory.service.byok.ByokGenerateService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.AopTestUtils;
import org.springframework.test.util.ReflectionTestUtils;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.when;

/**
 * MvService 分支覆盖测试（v2.15 C 批）。
 *
 * 未覆盖/跳过说明：
 * - L468(m1c3) render 字幕过滤：需走完真实渲染链路(ffmpeg/concat/mux)，mock 下断言脆弱，跳过。
 * - L587(m1c1) writeSrt 的 text null 三元：SectionTiming 是 private record，反射构造代价大，跳过。
 * - L608(m2c2)/L630(m1c1) muxAudio 分支：需 render 走到混音阶段，mock 下无意义，跳过。
 */
@SpringBootTest
class MvServiceBranchTest {

    @MockBean
    MvLyricsService mvLyricsService;
    @MockBean
    ByokGenerateService byokGenerateService;
    @MockBean
    FfmpegService ffmpegService;
    @MockBean
    AssetService assetService;

    @Autowired
    AssetRepository assetRepository;
    @Autowired
    MvService mvService;
    @Autowired
    MvSongRepository mvSongRepository;
    @Autowired
    MvTimelineService mvTimelineService;
    @Autowired
    AgentStepRepository agentStepRepository;
    @Autowired
    ObjectMapper objectMapper;

    // ---------- helpers ----------

    private Object target() {
        return AopTestUtils.getTargetObject(mvService);
    }

    private Object invokePrivate(Object target, String name, Class<?>[] types, Object... args) throws Exception {
        Method m = target.getClass().getDeclaredMethod(name, types);
        m.setAccessible(true);
        try {
            return m.invoke(target, args);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause instanceof RuntimeException re) {
                throw re;
            }
            if (cause instanceof Error err) {
                throw err;
            }
            throw new RuntimeException(cause);
        }
    }

    private Long createSongWithLyrics(String lyricsJson) {
        Long songId = mvService.create("主题", "mood", "style");
        MvSong song = mvSongRepository.findById(songId).orElseThrow();
        song.setLyricsJson(lyricsJson);
        mvSongRepository.save(song);
        return songId;
    }

    private Asset saveAsset(String filePath) {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath(filePath);
        return assetRepository.save(asset);
    }

    // ---------- importAudio ----------

    // L142(m1c3): originalName 无 "." → ext 保持 "" → 抛"仅支持"
    @Test
    void branch2_importAudio_noExtension_throws() {
        MockMultipartFile file = new MockMultipartFile("file", "noext", "audio/mpeg", "x".getBytes());
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, "标题", null, null, null));
        assertTrue(ex.getMessage().contains("仅支持"));
    }

    // L145(m1c5): ext 的 || 链 → wav 通过，最终成功返回 status IMPORTED
    @Test
    void branch2_importAudio_wavPasses() {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath("missing.mp3");
        asset = assetRepository.save(asset);
        when(assetService.upload(any(), any(), any(), anyLong())).thenReturn(asset);
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);

        MockMultipartFile file = new MockMultipartFile("file", "a.wav", "audio/wav", "data".getBytes());
        MvSong song = mvService.importAudio(file, "标题", null, null, null);

        assertNotNull(song);
        assertEquals("IMPORTED", song.getStatus());
        assertNotNull(song.getTimelineJson());
    }

    // L145(m1c5): m4a 通过 + lyricsText=null → instrumental 分支，timelineJson 非空
    @Test
    void branch2_importAudio_m4aNullLyrics_instrumental() {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath("missing.mp3");
        asset = assetRepository.save(asset);
        when(assetService.upload(any(), any(), any(), anyLong())).thenReturn(asset);
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);

        MockMultipartFile file = new MockMultipartFile("file", "a.m4a", "audio/x-m4a", "data".getBytes());
        MvSong song = mvService.importAudio(file, "标题", null, null, null);

        assertEquals("IMPORTED", song.getStatus());
        assertNotNull(song.getTimelineJson());
        assertTrue(song.getTimelineJson().contains("sections"));
    }

    // L149(m3c3): mime 三元 → contentType 为 application/octet-stream 跳过 mime 校验，ext mp3 成功
    @Test
    void branch2_importAudio_octetStreamMime_skipsCheck() {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath("missing.mp3");
        asset = assetRepository.save(asset);
        when(assetService.upload(any(), any(), any(), anyLong())).thenReturn(asset);
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);

        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "application/octet-stream", "data".getBytes());
        MvSong song = mvService.importAudio(file, "标题", null, null, null);

        assertEquals("IMPORTED", song.getStatus());
    }

    // L149(m3c3): contentType 为 null → 跳过 mime 校验，成功
    @Test
    void branch2_importAudio_nullMime_skipsCheck() {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath("missing.mp3");
        asset = assetRepository.save(asset);
        when(assetService.upload(any(), any(), any(), anyLong())).thenReturn(asset);
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);

        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", null, "data".getBytes());
        MvSong song = mvService.importAudio(file, "标题", null, null, null);

        assertEquals("IMPORTED", song.getStatus());
    }

    // L151/152(m2c4/m3c3): ok 的 || 链 → contentType "audio/x-wav" (ext wav) 成功
    @Test
    void branch2_importAudio_xWavMime_passes() {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath("missing.mp3");
        asset = assetRepository.save(asset);
        when(assetService.upload(any(), any(), any(), anyLong())).thenReturn(asset);
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);

        MockMultipartFile file = new MockMultipartFile("file", "a.wav", "audio/x-wav", "data".getBytes());
        MvSong song = mvService.importAudio(file, "标题", null, null, null);

        assertEquals("IMPORTED", song.getStatus());
    }

    // L171(m1c1): durationMs<=0 → probeDurationSeconds 返回 0.0 → IllegalStateException("无法读取音频时长")
    @Test
    void branch2_importAudio_zeroDuration_throws() {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath("missing.mp3");
        asset = assetRepository.save(asset);
        when(assetService.upload(any(), any(), any(), anyLong())).thenReturn(asset);
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(0.0);

        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "audio/mpeg", "data".getBytes());
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvService.importAudio(file, "标题", null, null, null));
        assertEquals("无法读取音频时长", ex.getMessage());
    }

    // L176(m1c3): lyricsText 非空走 lyrics 路径 → lyricsJson 含"段落 1"
    @Test
    void branch2_importAudio_withLyricsText_buildsLyrics() {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath("missing.mp3");
        asset = assetRepository.save(asset);
        when(assetService.upload(any(), any(), any(), anyLong())).thenReturn(asset);
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);

        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "audio/mpeg", "data".getBytes());
        MvSong song = mvService.importAudio(file, "标题", "第一行\n\n第二行", null, null);

        assertEquals("IMPORTED", song.getStatus());
        assertNotNull(song.getLyricsJson());
        assertTrue(song.getLyricsJson().contains("段落 1"));
    }

    // L176(m1c3): lyricsText=" " 走 instrumental 分支 → timelineJson 非空
    @Test
    void branch2_importAudio_blankLyricsText_instrumental() {
        Asset asset = new Asset();
        asset.setFileName("test.mp3"); // FILE_NAME 列 NOT NULL
        asset.setType(AssetType.AUDIO);
        asset.setSource(AssetSource.UPLOADED); // TYPE/SOURCE 列 NOT NULL
        asset.setFilePath("missing.mp3");
        asset = assetRepository.save(asset);
        when(assetService.upload(any(), any(), any(), anyLong())).thenReturn(asset);
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);

        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "audio/mpeg", "data".getBytes());
        MvSong song = mvService.importAudio(file, "标题", " ", null, null);

        assertEquals("IMPORTED", song.getStatus());
        assertNotNull(song.getTimelineJson());
    }

    // ---------- buildLyricsJsonFromText ----------

    // L247(m1c1): 连续空行不产生空组 → "第一行\n\n\n第二行" 只有 2 段
    @Test
    void branch2_buildLyricsJson_consecutiveBlankLines_twoSections() throws Exception {
        String json = mvService.buildLyricsJsonFromText("t", "第一行\n\n\n第二行");
        JsonNode root = objectMapper.readTree(json);
        JsonNode sections = root.path("sections");
        assertTrue(sections.isArray());
        assertEquals(2, sections.size());
    }

    // L255(m1c1): 末尾空行不产生空组 → "第一行\n第二行\n\n" 无空行分段 → 每 4 行一段 = 1 段
    @Test
    void branch2_buildLyricsJson_trailingBlankLines_oneSection() throws Exception {
        String json = mvService.buildLyricsJsonFromText("t", "第一行\n第二行\n\n");
        JsonNode root = objectMapper.readTree(json);
        JsonNode sections = root.path("sections");
        assertTrue(sections.isArray());
        assertEquals(1, sections.size());
    }

    // ---------- compose ----------

    // L340(m1c1): sections 非数组 → 跳过遍历，随后 align() 因 sections 缺失抛"作词结果为空"
    // （dpsk 回喂轮曾整段编造 setSongId/generateJson 等不存在的 API，已弃用，改回最小修正）
    @Test
    void branch2_compose_sectionsNotArray_alignThrows() {
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);
        when(byokGenerateService.generate(any()))
                .thenReturn(new ByokGenerateService.GenerateResponse("SUCCEEDED", "http://x/a.mp3", null));

        Long songId = createSongWithLyrics("{\"title\":\"t\"}");
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.compose(songId, 1L, "m1"));
        assertTrue(ex.getMessage().contains("作词结果为空"));
    }

    // L345(m1c1): style null → prompt 以"曲风：，歌名："开头
    @Test
    void branch2_compose_nullStyle_promptPrefix() {
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(60.0);
        when(byokGenerateService.generate(any()))
                .thenReturn(new ByokGenerateService.GenerateResponse("SUCCEEDED", "http://x/a.mp3", null));

        Long songId = mvService.create("主题", null, null);
        MvSong song = mvSongRepository.findById(songId).orElseThrow();
        song.setLyricsJson("{\"title\":\"歌\",\"sections\":[{\"name\":\"段落 1\",\"lyrics\":\"第一行\",\"estSeconds\":8}]}"); // sections 不能为空数组，否则 align 抛"作词结果为空"走不到 byok
        mvSongRepository.save(song);

        mvService.compose(songId, 1L, "m1");

        ArgumentCaptor<ByokGenerateService.GenerateRequest> captor =
                ArgumentCaptor.forClass(ByokGenerateService.GenerateRequest.class);
        org.mockito.Mockito.verify(byokGenerateService).generate(captor.capture());
        String prompt = captor.getValue().prompt();
        assertTrue(prompt.startsWith("曲风：，歌名："), "prompt was: " + prompt);
    }

    // L352(m1c1): byok 非 SUCCEEDED 且 error null → RuntimeException 含"作曲失败：未知错误"，status FAILED
    @Test
    void branch2_compose_failedNullError_throwsAndSetsFailed() {
        when(byokGenerateService.generate(any()))
                .thenReturn(new ByokGenerateService.GenerateResponse("FAILED", null, null));

        Long songId = createSongWithLyrics("{\"title\":\"t\",\"sections\":[]}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> mvService.compose(songId, 1L, "m1"));
        assertTrue(ex.getMessage().contains("作曲失败：未知错误"));
        // 注意：compose 是 @Transactional，异常抛出后事务回滚，catch 块里 save 的 FAILED 状态会被回滚，
        // 故不在此断言 DB 状态（与既有测试 composeWithFailedByokThrowsAndSetsSongFailed 一致）。
    }

    // ---------- storyboard ----------

    // L377/378(m1c3): timelineJson="" 且 lyricsJson=null → 抛"请先生成歌词或导入音频"
    @Test
    void branch2_storyboard_emptyTimelineNullLyrics_throws() {
        Long songId = mvService.create("主题", "mood", "style");
        MvSong song = mvSongRepository.findById(songId).orElseThrow();
        song.setTimelineJson("");
        song.setLyricsJson(null);
        mvSongRepository.save(song);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvService.storyboard(songId));
        assertEquals("请先生成歌词或导入音频", ex.getMessage());
    }

    // L377/378(m1c3): timelineJson=null 且 lyricsJson=" " → 同样抛
    @Test
    void branch2_storyboard_nullTimelineBlankLyrics_throws() {
        Long songId = mvService.create("主题", "mood", "style");
        MvSong song = mvSongRepository.findById(songId).orElseThrow();
        song.setTimelineJson(null);
        song.setLyricsJson(" ");
        mvSongRepository.save(song);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvService.storyboard(songId));
        assertEquals("请先生成歌词或导入音频", ex.getMessage());
    }

    // ---------- loadTimeline (private) ----------

    // L529(m1c3): timelineJson="" → 走重算分支 → sections 非空
    @Test
    void branch2_loadTimeline_blankTimeline_recomputes() throws Exception {
        Long songId = mvService.create("主题", "mood", "style");
        MvSong song = mvSongRepository.findById(songId).orElseThrow();
        song.setTimelineJson("");
        song.setLyricsJson("{\"title\":\"t\",\"sections\":[{\"name\":\"段落 1\",\"mood\":\"\",\"estSeconds\":8,\"lyrics\":\"第一行\\n第二行\"}]}");
        song.setDurationMs(60000);
        mvSongRepository.save(song);

        Object result = invokePrivate(target(), "loadTimeline",
                new Class<?>[]{MvSong.class}, song);
        MvTimelineService.Timeline timeline = (MvTimelineService.Timeline) result;
        assertNotNull(timeline);
        assertTrue(!timeline.sections().isEmpty());
    }

    // ---------- resolveLocalAudio (private) ----------

    // L563(m1c3): 以 /api/assets/ 开头但不以 /file 结尾 → 抛"不支持的音频地址"
    @Test
    void branch2_resolveLocalAudio_assetsPrefixNoFileSuffix_throws() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> invokePrivate(target(), "resolveLocalAudio",
                        new Class<?>[]{String.class}, "/api/assets/123"));
        assertEquals("不支持的音频地址", ex.getMessage());
    }
}
