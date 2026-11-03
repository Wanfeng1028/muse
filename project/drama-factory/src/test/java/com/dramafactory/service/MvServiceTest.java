package com.dramafactory.service;

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.MvSong;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.MvSongRepository;
import com.dramafactory.service.byok.ByokGenerateService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;

/**
 * MvService 集成测试。
 */
@SpringBootTest
class MvServiceTest {

    @Autowired
    private MvService mvService;

    @Autowired
    private MvSongRepository mvSongRepository;

    @Autowired
    private AgentStepRepository agentStepRepository;

    @MockBean
    private MvLyricsService mvLyricsService;

    @MockBean
    private ByokGenerateService byokGenerateService;

    private MvLyricsService.LyricsResult fixedLyrics() {
        return new MvLyricsService.LyricsResult(
                List.of(
                        new MvLyricsService.LyricSection("verse1", "测试歌词第一段", "欢快", 10),
                        new MvLyricsService.LyricSection("chorus1", "测试歌词副歌", "激昂", 10)
                ),
                "测试歌", 0, 0);
    }

    private void stubLyrics() {
        when(mvLyricsService.generate(anyString(), any(), any())).thenReturn(fixedLyrics());
        when(mvLyricsService.toJson(any())).thenReturn(
                "{\"title\":\"测试歌\",\"sections\":["
                + "{\"name\":\"verse1\",\"lyrics\":\"测试歌词第一段\",\"mood\":\"欢快\",\"estSeconds\":10},"
                + "{\"name\":\"chorus1\",\"lyrics\":\"测试歌词副歌\",\"mood\":\"激昂\",\"estSeconds\":10}]}");
    }

    @Test
    void createBlankThemeThrows() {
        assertThrows(IllegalArgumentException.class, () -> mvService.create("", "欢快", "流行"));
        assertThrows(IllegalArgumentException.class, () -> mvService.create(null, "欢快", "流行"));
    }

    @Test
    void createNormalWritesAgentStepsInOrder() {
        Long songId = mvService.create("测试主题", "欢快", "流行");
        assertNotNull(songId);

        MvSong song = mvService.getById(songId);
        assertEquals("DRAFT", song.getStatus());
        assertNotNull(song.getRunId());

        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(song.getRunId());
        assertEquals(6, steps.size());
        assertEquals(AgentType.LYRICS, steps.get(0).getAgentType());
        assertEquals(AgentType.COMPOSE, steps.get(1).getAgentType());
        assertEquals(AgentType.BOARD, steps.get(2).getAgentType());
        assertEquals(AgentType.VIDEO, steps.get(3).getAgentType());
        assertEquals(AgentType.EDIT, steps.get(4).getAgentType());
        assertEquals(AgentType.QC, steps.get(5).getAgentType());
    }

    @Test
    void generateLyricsWritesJsonAndMarksDone() {
        stubLyrics();

        Long songId = mvService.create("作词测试", "抒情", "民谣");
        MvSong song = mvService.generateLyrics(songId);

        assertNotNull(song.getLyricsJson());
        assertTrue(song.getLyricsJson().contains("verse1"));
        assertEquals("LYRICS_DONE", song.getStatus());
    }

    @Test
    void composeWithoutLyricsThrows() {
        Long songId = mvService.create("无歌词作曲", null, null);
        assertThrows(IllegalStateException.class, () -> mvService.compose(songId, 1L, "music-3.0"));
    }

    @Test
    void composeSuccessMarksComposed() {
        stubLyrics();
        when(byokGenerateService.generate(any())).thenReturn(
                new ByokGenerateService.GenerateResponse("SUCCEEDED", "/api/byok/file/music/t.mp3", null));

        Long songId = mvService.create("作曲测试", "欢快", "流行");
        mvService.generateLyrics(songId);
        MvSong song = mvService.compose(songId, 1L, "music-3.0");

        assertEquals("COMPOSED", song.getStatus());
        assertEquals("/api/byok/file/music/t.mp3", song.getAudioUrl());
    }

    @Test
    void storyboardReturnsSectionsMatchingLyrics() {
        stubLyrics();

        Long songId = mvService.create("分镜测试", null, null);
        mvService.generateLyrics(songId);

        List<Map<String, String>> sections = mvService.storyboard(songId);
        assertNotNull(sections);
        assertEquals(2, sections.size());
        assertTrue(sections.get(0).containsKey("visualPrompt"));
    }

    @Test
    void renderWithoutAudioThrows() {
        stubLyrics();

        Long songId = mvService.create("无音频渲染", null, null);
        mvService.generateLyrics(songId);
        assertThrows(IllegalStateException.class, () -> mvService.render(songId, true));
    }

    @Test
    void getByIdNotFoundThrows() {
        assertThrows(com.dramafactory.exception.ResourceNotFoundException.class,
                () -> mvService.getById(999999L));
    }
}
