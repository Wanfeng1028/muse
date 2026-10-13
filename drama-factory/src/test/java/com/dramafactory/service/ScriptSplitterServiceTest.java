package com.dramafactory.service;

import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.model.CameraMove;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

/**
 * Unit tests for {@link ScriptSplitterService#parseShotsJson(Episode, String)} and the
 * package-visible helpers {@code stripCodeFence} / {@code text}.
 *
 * <p>No Spring context is started; all repositories are Mockito mocks.</p>
 */
class ScriptSplitterServiceTest {

    private ScriptSplitterService service;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        ShotRepository shotRepository = mock(ShotRepository.class);
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        service = new ScriptSplitterService(
                episodeRepository,
                shotRepository,
                videoTaskRepository,
                credentialResolver,
                objectMapper,
                "Deepseek-v4-flash",
                3000);
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
    void parseShotsJson_invalidCameraMove_labelYieldsNullCameraMove() {
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

        List<Shot> shots = service.parseShotsJson(episode(), content);

        assertEquals(1, shots.size());
        assertNull(shots.get(0).getCameraMove(),
                "CameraMove.fromLabel returns null for invalid labels; no exception expected");
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
}
