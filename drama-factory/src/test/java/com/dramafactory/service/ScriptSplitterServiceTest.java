package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.VideoTask;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;



/**
 * Unit tests for {@link ScriptSplitterService#parseShotsJson(Episode, String)} and the
 * package-visible helpers {@code stripCodeFence} / {@code text}.
 *
 * <p>No Spring context is started; all repositories are Mockito mocks.</p>
 */
class ScriptSplitterServiceTest {

    private EpisodeRepository episodeRepository;
    private ShotRepository shotRepository;
    private VideoTaskRepository videoTaskRepository;
    private CredentialResolver credentialResolver;

    private ScriptSplitterService service;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        episodeRepository = mock(EpisodeRepository.class);
        shotRepository = mock(ShotRepository.class);
        videoTaskRepository = mock(VideoTaskRepository.class);
        credentialResolver = mock(CredentialResolver.class);
        service = new ScriptSplitterService(
                episodeRepository,
                shotRepository,
                videoTaskRepository,
                credentialResolver,
                mock(SkillService.class),
                objectMapper,
                "Deepseek-v4-flash",
                3000, null);

    }



    private Episode episode() {
        Episode episode = new Episode();
        episode.setId(1L);
        return episode;
    }

    @Test
    void parseShotsJson_twoShots_parsesAllFields() {
        String content = """
                [
                  {
                    "shotNo": 1,
                    "shotSize": "特写",
                    "cameraMove": "推镜头",
                    "description": "主角特写",
                    "dialogue": "你好",
                    "videoPrompt": "close up shot",
                    "durationSeconds": 3
                  },
                  {
                    "shotNo": 2,
                    "shotSize": "远景",
                    "cameraMove": "跟镜头",
                    "description": "街道远景",
                    "dialogue": "再见",
                    "videoPrompt": "wide street shot",
                    "durationSeconds": 8
                  }
                ]
                """;

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(2, shots.size());

        Shot first = shots.get(0);
        assertEquals(1, first.getShotNo());
        assertEquals(ShotSize.TE_XIE, first.getShotSize());
        assertEquals(CameraMove.TUI, first.getCameraMove());
        assertEquals("主角特写", first.getDescription());
        assertEquals("你好", first.getDialogue());
        assertEquals("close up shot", first.getVideoPrompt());
        assertEquals(3, first.getDurationSeconds());

        Shot second = shots.get(1);
        assertEquals(2, second.getShotNo());
        assertEquals(ShotSize.YUAN_JING, second.getShotSize());
        assertEquals(CameraMove.GEN, second.getCameraMove());
        assertEquals("街道远景", second.getDescription());
        assertEquals("再见", second.getDialogue());
        assertEquals("wide street shot", second.getVideoPrompt());
        assertEquals(8, second.getDurationSeconds());
    }

    @Test
    void parseShotsJson_withCodeFence_stripsFenceAndParses() {
        String content = """
                ```json
                [
                  {
                    "shotNo": 1,
                    "shotSize": "中景",
                    "cameraMove": "固定机位",
                    "description": "对话中景",
                    "dialogue": "台词",
                    "videoPrompt": "medium shot",
                    "durationSeconds": 4
                  }
                ]
                ```
                """;

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(1, shots.size());
        Shot shot = shots.get(0);
        assertEquals(1, shot.getShotNo());
        assertEquals(ShotSize.ZHONG_JING, shot.getShotSize());
        assertEquals(CameraMove.GU_DING, shot.getCameraMove());
        assertEquals("对话中景", shot.getDescription());
        assertEquals("台词", shot.getDialogue());
        assertEquals("medium shot", shot.getVideoPrompt());
        assertEquals(4, shot.getDurationSeconds());
    }

    @Test
    void parseShotsJson_emptyArray_throws() {
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.parseShotsJson(episode(), "[]"));
        assertEquals("大模型未拆出任何分镜", ex.getMessage());
    }

    @Test
    void parseShotsJson_rootNotArray_throws() {
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.parseShotsJson(episode(), "{\"shots\":[]}"));
        assertEquals("大模型返回的不是 JSON 数组", ex.getMessage());
    }

    @Test
    void parseShotsJson_invalidJson_throws() {
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.parseShotsJson(episode(), "not json at all"));
        assertTrue(ex.getMessage().startsWith("解析大模型返回内容失败: "),
                "message should start with parse failure prefix, was: " + ex.getMessage());
    }

    @Test
    void parseShotsJson_invalidShotSizeOnSecondShot_throwsWithIndex() {
        String content = """
                [
                  {
                    "shotNo": 1,
                    "shotSize": "特写",
                    "cameraMove": "推镜头",
                    "description": "a",
                    "dialogue": "b",
                    "videoPrompt": "c",
                    "durationSeconds": 3
                  },
                  {
                    "shotNo": 2,
                    "shotSize": "巨幅",
                    "cameraMove": "推镜头",
                    "description": "d",
                    "dialogue": "e",
                    "videoPrompt": "f",
                    "durationSeconds": 3
                  }
                ]
                """;

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.parseShotsJson(episode(), content));
        assertEquals("第 2 个分镜的字段 shotSize 非法: 巨幅", ex.getMessage());
        assertTrue(ex.getMessage().contains("第 2 个分镜"));
    }

    @Test
    void parseShotsJson_invalidCameraMove_throwsWithClearMessage() {
        String content = """
                [
                  {
                    "shotNo": 1,
                    "shotSize": "近景",
                    "cameraMove": "旋转飞行",
                    "description": "a",
                    "dialogue": "b",
                    "videoPrompt": "c",
                    "durationSeconds": 3
                  }
                ]
                """;

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.parseShotsJson(episode(), content));
        assertEquals("第 1 个分镜的字段 cameraMove 非法: 旋转飞行", ex.getMessage());
        assertTrue(ex.getMessage().contains("第 1 个分镜"));
    }

    @Test
    void parseShotsJson_missingShotNo_usesArrayIndexStartingAtOne() {
        String content = """
                [
                  {
                    "shotSize": "全景",
                    "cameraMove": "摇镜头",
                    "description": "a",
                    "dialogue": "b",
                    "videoPrompt": "c",
                    "durationSeconds": 3
                  },
                  {
                    "shotSize": "远景",
                    "cameraMove": "移镜头",
                    "description": "d",
                    "dialogue": "e",
                    "videoPrompt": "f",
                    "durationSeconds": 4
                  }
                ]
                """;

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(2, shots.size());
        assertEquals(1, shots.get(0).getShotNo());
        assertEquals(2, shots.get(1).getShotNo());
    }

    @Test
    void parseShotsJson_missingDurationSeconds_defaultsToFive() {
        String content = """
                [
                  {
                    "shotNo": 1,
                    "shotSize": "中景",
                    "cameraMove": "升降",
                    "description": "a",
                    "dialogue": "b",
                    "videoPrompt": "c"
                  }
                ]
                """;

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(1, shots.size());
        assertEquals(5, shots.get(0).getDurationSeconds());
    }

    @Test
    void text_missingField_returnsNull() {
        JsonNode node = objectMapper.createObjectNode();
        assertNull(ScriptSplitterService.text(node, "shotSize"));
        assertNull(ScriptSplitterService.text(node, "notPresentAtAll"));
    }

    @Test
    void text_nullField_returnsNull() {
        JsonNode node = objectMapper.createObjectNode();
        ((com.fasterxml.jackson.databind.node.ObjectNode) node).putNull("dialogue");
        assertNull(ScriptSplitterService.text(node, "dialogue"));
    }

    @Test
    void stripCodeFence_noFence_trimsOnly() {
        String raw = "  [ {\"a\":1} ]  ";
        assertEquals("[ {\"a\":1} ]", ScriptSplitterService.stripCodeFence(raw));
    }

    @Test
    void stripCodeFence_onlyLeadingFence() {
        String raw = "```json\n[1,2,3]";
        assertEquals("[1,2,3]", ScriptSplitterService.stripCodeFence(raw));
    }

    @Test
    void stripCodeFence_bothFences() {
        String raw = "```json\n[1,2,3]\n```";
        assertEquals("[1,2,3]", ScriptSplitterService.stripCodeFence(raw));
    }

    @Test
    void stripCodeFence_bothFencesWithSurroundingWhitespace() {
        String raw = "\n```json\n[1,2,3]\n```\n";
        assertEquals("[1,2,3]", ScriptSplitterService.stripCodeFence(raw));
    }

    @Test
    void stripCodeFence_fenceWithoutNewline_stripsThreeChars() {
        String raw = "```[1,2,3]";
        assertEquals("[1,2,3]", ScriptSplitterService.stripCodeFence(raw));
    }

    @Test
    void parseShotsJson_stringShotNo_fallsBackToIndex() {
        String content = """
                [
                  {
                    "shotNo": "x",
                    "shotSize": "特写",
                    "cameraMove": "推镜头",
                    "description": "a",
                    "dialogue": "b",
                    "videoPrompt": "c",
                    "durationSeconds": 3
                  }
                ]
                """;

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(1, shots.size());
        assertEquals(1, shots.get(0).getShotNo());
    }

    @Test
    void parseShotsJson_stringDurationSeconds_defaultsToFive() {
        String content = """
                [
                  {
                    "shotNo": 1,
                    "shotSize": "特写",
                    "cameraMove": "推镜头",
                    "description": "a",
                    "dialogue": "b",
                    "videoPrompt": "c",
                    "durationSeconds": "3"
                  }
                ]
                """;

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(1, shots.size());
        assertEquals(5, shots.get(0).getDurationSeconds());
    }

    @Test
    void parseShotsJson_missingCameraMove_yieldsNull() {
        String content = """
                [
                  {
                    "shotNo": 1,
                    "shotSize": "特写",
                    "description": "a",
                    "dialogue": "b",
                    "videoPrompt": "c",
                    "durationSeconds": 3
                  }
                ]
                """;

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(1, shots.size());
        assertNull(shots.get(0).getCameraMove());
    }

    @Test
    void parseShotsJson_missingShotSize_throwsWithNullLabel() {
        String content = """
                [
                  {
                    "shotNo": 1,
                    "cameraMove": "推镜头",
                    "description": "a",
                    "dialogue": "b",
                    "videoPrompt": "c",
                    "durationSeconds": 3
                  }
                ]
                """;

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.parseShotsJson(episode(), content));
        assertEquals("第 1 个分镜的字段 shotSize 非法: null", ex.getMessage());
    }

    @Test
    void parseShotsJson_numericDescription_coercedToText() {
        String content = """
                [
                  {
                    "shotNo": 1,
                    "shotSize": "特写",
                    "cameraMove": "推镜头",
                    "description": 123,
                    "dialogue": "b",
                    "videoPrompt": "c",
                    "durationSeconds": 3
                  }
                ]
                """;

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(1, shots.size());
        assertEquals("123", shots.get(0).getDescription());
    }

    private Records.ShotBatchItem validItem() {
        return new Records.ShotBatchItem(1, "特写", "推镜头", "d", 5, "dlg", "vp");
    }

    private Records.ShotBatchItem item(Integer shotNo, String shotSize, String cameraMove,
                                       String description, Integer durationSeconds,
                                       String dialogue, String videoPrompt) {
        return new Records.ShotBatchItem(shotNo, shotSize, cameraMove, description,
                durationSeconds, dialogue, videoPrompt);
    }

    private void stubEpisodeFound() {
        Episode ep = episode();
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(ep));
    }

    @Test
    void replaceShots_episodeMissing_throws() {
        when(episodeRepository.findById(1L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class,
                () -> service.replaceShots(1L, List.of(validItem())));
    }

    @Test
    void replaceShots_nullItems_throws() {
        stubEpisodeFound();

        assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L, null));
    }

    @Test
    void replaceShots_emptyItems_throws() {
        stubEpisodeFound();

        assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L, List.of()));
    }

    @Test
    void replaceShots_tooManyItems_throws() {
        stubEpisodeFound();

        List<Records.ShotBatchItem> items = new ArrayList<>();
        for (int i = 0; i < 31; i++) {
            items.add(validItem());
        }

        assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L, items));
    }

    @Test
    void replaceShots_happyPath_replacesOldShots() {
        stubEpisodeFound();

        Shot oldShot = new Shot();
        oldShot.setId(100L);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(oldShot));
        when(videoTaskRepository.findByShotIdOrderByIdDesc(100L)).thenReturn(List.of(new VideoTask()));
        when(shotRepository.save(any(Shot.class))).thenAnswer(inv -> inv.getArgument(0));

        List<Records.ShotResponse> resp = service.replaceShots(1L,
                List.of(validItem(), item(2, "远景", "跟镜头", "d2", 8, "dlg2", "vp2")));

        assertEquals(2, resp.size());
        assertEquals(1, resp.get(0).shotNo());
        assertEquals("特写", resp.get(0).shotSizeLabel());
        assertEquals("推镜头", resp.get(0).cameraMoveLabel());

        verify(videoTaskRepository).deleteAll(any());
        verify(shotRepository).delete(oldShot);
        verify(shotRepository, times(2)).save(any(Shot.class));

        org.mockito.ArgumentCaptor<Episode> captor = org.mockito.ArgumentCaptor.forClass(Episode.class);
        verify(episodeRepository).save(captor.capture());
        assertEquals(EpisodeStatus.SCRIPTED, captor.getValue().getStatus());
    }

    @Test
    void replaceShots_missingShotNo_throwsWithIndex() {
        stubEpisodeFound();

        List<Records.ShotBatchItem> items = List.of(
                validItem(),
                item(null, "特写", "推镜头", "d", 5, "dlg", "vp"));

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L, items));
        assertTrue(ex.getMessage().contains("第 2 个分镜缺少镜号"),
                "message should contain missing shotNo hint, was: " + ex.getMessage());
    }

    @Test
    void replaceShots_illegalShotSize_throws() {
        stubEpisodeFound();

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L,
                        List.of(item(1, "巨幅", "推镜头", "d", 5, "dlg", "vp"))));
        assertTrue(ex.getMessage().contains("景别非法"),
                "message should contain illegal shotSize hint, was: " + ex.getMessage());
    }

    @Test
    void replaceShots_illegalCameraMove_throws() {
        stubEpisodeFound();

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L,
                        List.of(item(1, "特写", "旋转飞行", "d", 5, "dlg", "vp"))));
        assertTrue(ex.getMessage().contains("运镜非法"),
                "message should contain illegal cameraMove hint, was: " + ex.getMessage());
    }

    @Test
    void replaceShots_nullCameraMove_throws() {
        stubEpisodeFound();

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L,
                        List.of(item(1, "特写", null, "d", 5, "dlg", "vp"))));
        assertTrue(ex.getMessage().contains("运镜非法"),
                "message should contain illegal cameraMove hint, was: " + ex.getMessage());
    }

    @Test
    void replaceShots_nullDuration_defaultsToFive() {
        stubEpisodeFound();
        when(shotRepository.save(any(Shot.class))).thenAnswer(inv -> inv.getArgument(0));

        service.replaceShots(1L, List.of(item(1, "特写", "推镜头", "d", null, "dlg", "vp")));

        org.mockito.ArgumentCaptor<Shot> captor = org.mockito.ArgumentCaptor.forClass(Shot.class);
        verify(shotRepository).save(captor.capture());
        assertEquals(5, captor.getValue().getDurationSeconds());
    }

    @Test
    void replaceShots_zeroDuration_throws() {
        stubEpisodeFound();

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L,
                        List.of(item(1, "特写", "推镜头", "d", 0, "dlg", "vp"))));
        assertTrue(ex.getMessage().contains("时长非法"),
                "message should contain illegal duration hint, was: " + ex.getMessage());
    }

    @Test
    void replaceShots_tooLongDuration_throws() {
        stubEpisodeFound();

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.replaceShots(1L,
                        List.of(item(1, "特写", "推镜头", "d", 31, "dlg", "vp"))));
        assertTrue(ex.getMessage().contains("时长非法"),
                "message should contain illegal duration hint, was: " + ex.getMessage());
    }

    @Test
    void splitFromScript_episodeMissing_throws() {
        when(episodeRepository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class,
                () -> service.splitFromScript(99L, "剧本原文"));
    }

    @Test
    void splitFromScript_blankScript_throws() {
        stubEpisodeFound();

        assertThrows(IllegalArgumentException.class,
                () -> service.splitFromScript(1L, "   "));
    }
}


