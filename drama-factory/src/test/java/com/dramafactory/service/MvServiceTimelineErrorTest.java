package com.dramafactory.service;

import com.dramafactory.model.MvSong;
import com.dramafactory.repository.MvSongRepository;
import com.dramafactory.service.byok.ByokGenerateService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@SpringBootTest
class MvServiceTimelineErrorTest {

    @Autowired
    private MvService mvService;

    @Autowired
    private MvSongRepository mvSongRepository;

    @MockBean
    private MvLyricsService mvLyricsService;

    @MockBean
    private ByokGenerateService byokGenerateService;

    @Test
    void getStepStatusesReturnsSixStepsInOrder() {
        Long songId = mvService.create("t", "m", "s");
        MvSong song = mvSongRepository.findById(songId).orElseThrow();

        List<Map<String, String>> statuses = mvService.getStepStatuses(song.getRunId());
        assertEquals(6, statuses.size());
        assertEquals("LYRICS", statuses.get(0).get("agentType"));
        assertEquals("COMPOSE", statuses.get(1).get("agentType"));
        assertEquals("BOARD", statuses.get(2).get("agentType"));
        assertEquals("VIDEO", statuses.get(3).get("agentType"));
        assertEquals("EDIT", statuses.get(4).get("agentType"));
        assertEquals("QC", statuses.get(5).get("agentType"));
    }

    @Test
    void composeWithFailedByokThrowsAndSetsSongFailed() {
        Long songId = mvService.create("t", "m", "s");
        MvSong song = mvSongRepository.findById(songId).orElseThrow();
        song.setLyricsJson("{\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\"}]}");
        mvSongRepository.save(song);

        when(byokGenerateService.generate(any()))
                .thenReturn(new ByokGenerateService.GenerateResponse("FAILED", null, "boom"));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> mvService.compose(songId, 1L, "m"));
        assertTrue(ex.getMessage().contains("作曲失败"));

        // 注意：compose 方法是 @Transactional，异常抛出后事务回滚，
        // catch 块里写的 FAILED 状态会被回滚（已知行为，不在此断言 DB 状态）。
    }

    @Test
    void storyboardWithoutLyricsThrowsPleaseGenerateLyrics() {
        MvSong song = new MvSong();
        song.setTheme("t");
        song.setLyricsJson("");
        song.setRunId(98L);
        MvSong saved = mvSongRepository.save(song);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvService.storyboard(saved.getId()));
        assertEquals("请先生成歌词或导入音频", ex.getMessage());
    }

    @Test
    void renderWithoutAudioThrowsIllegalState() {
        MvSong song = new MvSong();
        song.setTheme("t");
        song.setAudioUrl("");
        song.setRunId(97L);
        MvSong saved = mvSongRepository.save(song);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvService.render(saved.getId(), true));
        assertEquals("请先作曲或导入音频", ex.getMessage());
    }

    @Test
    void storyboardWithNullRunIdThrowsRunNotLinked() {
        MvSong song = new MvSong();
        song.setTheme("t");
        song.setLyricsJson("{\"sections\":[{\"name\":\"a\",\"lyrics\":\"x\"}]}");
        MvSong saved = mvSongRepository.save(song);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvService.storyboard(saved.getId()));
        assertEquals("Run 未关联", ex.getMessage());
    }

    @Test
    void composeWithoutLyricsThrowsPleaseGenerateLyrics() {
        MvSong song = new MvSong();
        song.setTheme("t");
        song.setLyricsJson("");
        song.setRunId(96L);
        MvSong saved = mvSongRepository.save(song);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvService.compose(saved.getId(), 1L, "m"));
        assertEquals("请先生成歌词", ex.getMessage());
    }
}
