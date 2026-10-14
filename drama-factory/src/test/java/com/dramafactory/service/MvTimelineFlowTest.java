package com.dramafactory.service;

import com.dramafactory.model.MvSong;
import com.dramafactory.service.byok.ByokGenerateService;
import com.dramafactory.repository.MvSongRepository;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Map;

@SpringBootTest
class MvTimelineFlowTest {

    private static final String LYRICS_JSON = "{\"title\":\"测试歌\",\"sections\":[{\"name\":\"verse1\",\"lyrics\":\"第一行\\n第二行\\n第三行\",\"mood\":\"欢快\",\"estSeconds\":10},{\"name\":\"chorus1\",\"lyrics\":\"副歌第一句\\n副歌第二句\",\"mood\":\"激昂\",\"estSeconds\":10}]}";

    @Autowired
    private MvService mvService;

    @Autowired
    private MvSongRepository mvSongRepository;

    @MockBean
    private MvLyricsService mvLyricsService;

    @MockBean
    private ByokGenerateService byokGenerateService;

    private Path audioPath;

    @BeforeEach
    void setUp() throws Exception {
        Mockito.when(mvLyricsService.generate(ArgumentMatchers.anyString(), ArgumentMatchers.any(), ArgumentMatchers.any()))
                .thenReturn(new MvLyricsService.LyricsResult(
                        List.of(
                                new MvLyricsService.LyricSection("verse1", "第一行\n第二行\n第三行", "欢快", 10),
                                new MvLyricsService.LyricSection("chorus1", "副歌第一句\n副歌第二句", "激昂", 10)),
                        "测试歌", 0, 0));
        Mockito.when(mvLyricsService.toJson(ArgumentMatchers.any())).thenReturn(LYRICS_JSON);
        Mockito.when(byokGenerateService.generate(ArgumentMatchers.any()))
                .thenReturn(new ByokGenerateService.GenerateResponse("SUCCEEDED", "/api/byok/file/music/mvtest.mp3", null));

        audioPath = Paths.get("./data/media/byok/music/mvtest.mp3");
        Files.createDirectories(audioPath.getParent());
        if (Files.exists(audioPath) && Files.size(audioPath) > 0) {
            return;
        }
        ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                "-c:a", "libmp3lame", "-ar", "44100", audioPath.toAbsolutePath().toString());
        pb.redirectErrorStream(true);
        Process process = pb.start();
        process.getInputStream().readAllBytes();
        int code = process.waitFor();
        if (code != 0) {
            Assertions.fail("ffmpeg 生成测试音频失败, exitCode=" + code);
        }
    }

    private Long prepareComposedSong() {
        Long songId = mvService.create("主题", "情绪", "风格");
        mvService.generateLyrics(songId);
        mvService.compose(songId, null, null);
        return songId;
    }

    @Test
    void composePersistsTimeline() {
        Long songId = prepareComposedSong();
        MvSong song = mvSongRepository.findById(songId).orElse(null);
        Assertions.assertNotNull(song);
        String timelineJson = song.getTimelineJson();
        Assertions.assertNotNull(timelineJson);
        Assertions.assertTrue(timelineJson.contains("\"totalMs\":8000"), "timeline 应包含 totalMs 8000, 实际: " + timelineJson);
        Assertions.assertTrue(timelineJson.contains("\"scaleFactor\":0.4"), "timeline 应包含 scaleFactor 0.4, 实际: " + timelineJson);
        Assertions.assertEquals("COMPOSED", song.getStatus());
    }

    @Test
    void storyboardDrivenByTimeline() {
        Long songId = prepareComposedSong();
        List<Map<String, String>> entries = mvService.storyboard(songId);
        Assertions.assertNotNull(entries);
        Assertions.assertEquals(5, entries.size());

        Assertions.assertEquals("0", entries.get(0).get("startMs"));
        Assertions.assertEquals("8000", entries.get(entries.size() - 1).get("endMs"));

        long sum = 0L;
        for (Map<String, String> entry : entries) {
            long duration = Long.parseLong(entry.get("durationMs"));
            Assertions.assertTrue(duration >= 800, "durationMs 应 >= 800, 实际: " + duration);
            sum += duration;
        }
        Assertions.assertEquals(8000L, sum);
    }

    @Test
    void renderWritesPerLineSrt() throws IOException {
        Long songId = prepareComposedSong();
        mvService.render(songId, true);

        Path srtPath = Paths.get("./data/media/mv", songId.toString(), "subs.srt");
        Assertions.assertTrue(Files.exists(srtPath), "subs.srt 应存在: " + srtPath);
        String srt = Files.readString(srtPath, StandardCharsets.UTF_8);
        int count = 0;
        int idx = 0;
        while ((idx = srt.indexOf("-->", idx)) >= 0) {
            count++;
            idx += 3;
        }
        Assertions.assertEquals(5, count, "subs.srt 应包含 5 个 -->, 实际: " + count);
        Assertions.assertTrue(srt.contains("第一行"), "subs.srt 应包含第一行");
        Assertions.assertTrue(srt.contains("副歌第二句"), "subs.srt 应包含副歌第二句");

        Path finalMp4 = Paths.get("./data/media/mv", songId.toString(), "final.mp4");
        Assertions.assertTrue(Files.exists(finalMp4), "final.mp4 应存在: " + finalMp4);
    }

    @Test
    void finalVideoDurationMatchesAudio() throws Exception {
        Long songId = prepareComposedSong();
        mvService.render(songId, true);

        Path finalMp4 = Paths.get("./data/media/mv", songId.toString(), "final.mp4");
        Assertions.assertTrue(Files.exists(finalMp4), "final.mp4 应存在: " + finalMp4);

        ProcessBuilder pb = new ProcessBuilder(
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", finalMp4.toAbsolutePath().toString());
        pb.redirectErrorStream(true);
        Process process = pb.start();
        byte[] out = process.getInputStream().readAllBytes();
        int code = process.waitFor();
        if (code != 0) {
            Assertions.fail("ffprobe 执行失败, exitCode=" + code + ", output=" + new String(out, StandardCharsets.UTF_8));
        }
        String text = new String(out, StandardCharsets.UTF_8).trim();
        Assertions.assertFalse(text.isEmpty(), "ffprobe 输出为空");
        double duration = Double.parseDouble(text);
        Assertions.assertTrue(Math.abs(duration - 8.0) < 1.5, "final.mp4 时长应接近 8.0, 实际: " + duration);
    }
}
