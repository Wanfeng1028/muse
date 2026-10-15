package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.MvSongRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.byok.ByokGenerateService;
import com.dramafactory.service.AssetService;
import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.FfmpegService;
import com.dramafactory.service.SkillService;
import com.dramafactory.tools.service.QuickToolsService;
import com.dramafactory.tools.service.ToolOpLogService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * V224B 服务分支补充（由 BranchMixedV224BTest 拆分，包可见成员需同包）。
 */
class ServiceBranchV224BTest {

    @Test
    void splitFromScript_episodeTitleNull_putsEmptyTitleIntoVars() {
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        ShotRepository shotRepository = mock(ShotRepository.class);
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        SkillService skillService = mock(SkillService.class);

        Episode episodeMock = mock(Episode.class);
        when(episodeMock.getTitle()).thenReturn(null);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episodeMock));

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, String>> varsCaptor =
                ArgumentCaptor.forClass((Class<Map<String, String>>) (Class<?>) Map.class);

        // resolveForUse 在 139 行抛异常，137 行 put 已执行完毕；用真实行为打断流程
        when(skillService.resolveForUse(anyLong(), varsCaptor.capture()))
                .thenThrow(new IllegalStateException("Skill 尚未安装"));

        ScriptSplitterService service = new ScriptSplitterService(
                episodeRepository,
                shotRepository,
                videoTaskRepository,
                credentialResolver,
                skillService,
                new ObjectMapper(),
                "Deepseek-v4-flash",
                3000,
                request -> {
                    throw new IllegalStateException("不应走到网络调用");
                });

        assertThrows(IllegalStateException.class,
                () -> service.splitFromScript(1L, "第一场", 1L));

        Map<String, String> captured = varsCaptor.getValue();
        assertNotNull(captured);
        assertEquals("", captured.get("剧集标题"));
    }

    // ---------------------------------------------------------------
    // 4. ScriptSplitterService#callModel catch(RuntimeException) 重抛臂
    // ---------------------------------------------------------------

    @Test
    void callModel_choicesMissing_rethrowsRuntimeExceptionWithEmptyMessage() throws Exception {
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        ShotRepository shotRepository = mock(ShotRepository.class);
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        SkillService skillService = mock(SkillService.class);

        lenient().when(credentialResolver.chatAuth()).thenReturn(null);

        Episode episode = new Episode();
        episode.setId(1L);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));

        @SuppressWarnings("unchecked")
        HttpResponse<String> httpResponse = mock(HttpResponse.class);
        when(httpResponse.statusCode()).thenReturn(200);
        when(httpResponse.body()).thenReturn("{\"nope\":true}");

        ScriptSplitterService.HttpExchange exchange = request -> httpResponse;

        ScriptSplitterService service = new ScriptSplitterService(
                episodeRepository,
                shotRepository,
                videoTaskRepository,
                credentialResolver,
                skillService,
                new ObjectMapper(),
                "Deepseek-v4-flash",
                3000,
                exchange);

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.splitFromScript(1L, "剧本"));
        assertEquals("大模型返回内容为空", ex.getMessage());
    }

    // ---------------------------------------------------------------
    // 5. MvService#buildLyricsJsonFromText 末尾空行 !cur.isEmpty() false 臂
    // ---------------------------------------------------------------

    @Test
    void buildLyricsJsonFromText_trailingBlankLine_skipsFinalAdd() throws Exception {
        MvService service = new MvService(
                mock(MvSongRepository.class),
                mock(RunRepository.class),
                mock(AgentStepRepository.class),
                mock(MvLyricsService.class),
                mock(ByokGenerateService.class),
                mock(FfmpegService.class),
                mock(MvTimelineService.class),
                new ObjectMapper(),
                mock(AssetService.class),
                mock(AssetRepository.class));

        String lyricsJson = service.buildLyricsJsonFromText("t", "第一段歌词\n\n第二段歌词\n\n");
        assertNotNull(lyricsJson);

        JsonNode root = new ObjectMapper().readTree(lyricsJson);
        JsonNode sections = root.get("sections");
        assertNotNull(sections);
        assertTrue(sections.isArray());
        assertEquals(2, sections.size());
    }

    // ---------------------------------------------------------------
    // 6. QuickToolsService#batchRenameAssets len>200 臂
    // ---------------------------------------------------------------

    @Test
    void batchRenameAssets_nameLength201_throwsIllegalArgument() {
        QuickToolsService service = new QuickToolsService(
                mock(AssetRepository.class),
                mock(AssetService.class),
                mock(FfmpegService.class),
                mock(ShotRepository.class),
                mock(EpisodeRepository.class),
                mock(ToolOpLogService.class),
                "./data/media");

        Map<Long, String> renames = new HashMap<>();
        renames.put(1L, "x".repeat(201));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.batchRenameAssets(renames));
        assertEquals("新文件名长度必须在 1~200 之间", ex.getMessage());
    }

    // ---------------------------------------------------------------
    // 7. QuickToolsService#exportShotCsv shotNo==null 臂
    // ---------------------------------------------------------------

    @Test
    void exportShotCsv_shotNoNull_rendersEmptyCell(@TempDir Path tempDir) {
        AssetRepository assetRepository = mock(AssetRepository.class);
        AssetService assetService = mock(AssetService.class);
        FfmpegService ffmpegService = mock(FfmpegService.class);
        ShotRepository shotRepository = mock(ShotRepository.class);
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        ToolOpLogService toolOpLogService = mock(ToolOpLogService.class);

        QuickToolsService service = new QuickToolsService(
                assetRepository,
                assetService,
                ffmpegService,
                shotRepository,
                episodeRepository,
                toolOpLogService,
                tempDir.toString());

        Episode episode = mock(Episode.class);
        when(episodeRepository.findById(9L)).thenReturn(Optional.of(episode));

        Shot shotMock = mock(Shot.class);
        when(shotMock.getShotNo()).thenReturn(null);
        when(shotMock.getShotSize()).thenReturn(ShotSize.ZHONG_JING);
        when(shotMock.getCameraMove()).thenReturn(CameraMove.GU_DING);
        when(shotMock.getDescription()).thenReturn("画面描述");
        when(shotMock.getDialogue()).thenReturn("台词");
        when(shotMock.getDurationSeconds()).thenReturn(5);
        when(shotMock.getCreatedAt()).thenReturn(LocalDateTime.of(2024, 1, 1, 0, 0));

        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(9L)).thenReturn(List.of(shotMock));

        byte[] bytes = service.exportShotCsv(9L);
        assertNotNull(bytes);

        String csv = new String(bytes, StandardCharsets.UTF_8);
        // 去掉 BOM 便于断言
        String body = csv.startsWith("\uFEFF") ? csv.substring(1) : csv;
        String[] lines = body.split("\r\n");

        assertTrue(lines[0].contains("镜号"), "首行应含 镜号，实际=" + lines[0]);
        // 第二行：shotNo 为 null → 空串，故以 ",ZHONG_JING" 开头（首列为空）
        assertTrue(lines[1].startsWith(",ZHONG_JING"),
                "第二行应以 ,ZHONG_JING 开头，实际=" + lines[1]);
    }
}
