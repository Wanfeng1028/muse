package com.dramafactory.service;

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.MvSong;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.service.byok.ByokGenerateService;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * 导入已有音频（IMPORT 模式）全流程集成测试。
 */
@SpringBootTest
class MvImportFlowTest {

    private static final Path TEST_AUDIO_DIR = Paths.get("./data/media/import-test");
    private static final Path TEST_WAV = TEST_AUDIO_DIR.resolve("import-flow-test.wav");

    @Autowired
    private MvService mvService;

    @Autowired
    private AgentStepRepository agentStepRepository;

    @MockBean
    private MvLyricsService mvLyricsService;

    @MockBean
    private ByokGenerateService byokGenerateService;

    private static final java.util.List<Long> CREATED_SONG_IDS =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    @AfterAll
    static void cleanUpRenderedDirs() {
        for (Long id : CREATED_SONG_IDS) {
            Path dir = Paths.get("./data/media/mv/" + id);
            if (Files.exists(dir)) {
                try (var stream = Files.walk(dir)) {
                    for (Path p : (Iterable<Path>) stream.sorted(java.util.Comparator.reverseOrder())::iterator) {
                        Files.deleteIfExists(p);
                    }
                } catch (IOException ignored) {
                }
            }
        }
        CREATED_SONG_IDS.clear();
    }

    @BeforeEach
    void setUp() throws IOException, InterruptedException {
        Files.createDirectories(TEST_AUDIO_DIR);
        if (Files.exists(TEST_WAV) && Files.size(TEST_WAV) > 0) {
            return;
        }
        ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "sine=frequency=440:duration=10",
                "-c:a", "pcm_s16le",
                TEST_WAV.toString());
        pb.redirectErrorStream(true);
        Process process = pb.start();
        int exit = process.waitFor();
        assertThat(exit)
                .as("ffmpeg 生成测试音频应成功")
                .isZero();
        assertThat(TEST_WAV).exists();
        assertThat(Files.size(TEST_WAV)).isGreaterThan(0L);
    }

    private MockMultipartFile buildWavFile() throws IOException {
        byte[] bytes = Files.readAllBytes(TEST_WAV);
        return new MockMultipartFile("file", "song.wav", "audio/wav", bytes);
    }

    @Test
    void importAudioWithLyrics() throws IOException {
        MockMultipartFile file = buildWavFile();
        String lyricsText = "第一句\n第二句\n\n副歌句";

        MvSong song = mvService.importAudio(file, "测试歌曲", lyricsText, "happy", "pop");
        CREATED_SONG_IDS.add(song.getId());

        assertThat(song).isNotNull();
        assertThat(song.getId()).isNotNull();
        assertThat(song.getSource()).isEqualTo("IMPORT");
        assertThat(song.getStatus()).isEqualTo("IMPORTED");
        assertThat(song.getAudioUrl()).startsWith("/api/assets/");
        assertThat(song.getDurationMs()).isNotNull();
        assertThat(song.getDurationMs()).isBetween(9000, 11000);
        assertThat(song.getLyricsJson()).isNotNull();
        assertThat(song.getLyricsJson()).contains("段落 1");
        assertThat(song.getTimelineJson()).isNotNull();
        assertThat(song.getTimelineJson()).isNotBlank();

        Long runId = song.getRunId();
        assertThat(runId).isNotNull();
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        assertThat(steps).hasSize(6);

        AgentStep step1 = steps.get(0);
        AgentStep step2 = steps.get(1);
        AgentStep step3 = steps.get(2);

        assertThat(step1.getStatus()).isEqualTo(AgentStepStatus.SKIPPED);
        assertThat(step1.getOutputSummary()).contains("已跳过作词作曲");
        assertThat(step2.getStatus()).isEqualTo(AgentStepStatus.SKIPPED);
        assertThat(step2.getOutputSummary()).contains("已跳过作词作曲");
        assertThat(step3.getStatus()).isEqualTo(AgentStepStatus.PENDING);

        List<Map<String, String>> storyboard = mvService.storyboard(song.getId());
        assertThat(storyboard).hasSize(3);

        MvSong rendered = mvService.render(song.getId(), true);
        assertThat(rendered).isNotNull();

        Path mvDir = Paths.get("./data/media/mv/" + song.getId());
        Path finalMp4 = mvDir.resolve("final.mp4");
        Path subsSrt = mvDir.resolve("subs.srt");

        assertThat(finalMp4).exists();
        assertThat(subsSrt).exists();
        String srtContent = new String(Files.readAllBytes(subsSrt));
        assertThat(srtContent).contains("第一句");
    }

    @Test
    void importAudioInstrumental() throws IOException {
        MockMultipartFile file = buildWavFile();

        MvSong song = mvService.importAudio(file, "纯音乐", null, "calm", "ambient");
        CREATED_SONG_IDS.add(song.getId());

        assertThat(song).isNotNull();
        assertThat(song.getSource()).isEqualTo("IMPORT");
        assertThat(song.getStatus()).isEqualTo("IMPORTED");

        List<Map<String, String>> storyboard = mvService.storyboard(song.getId());
        assertThat(storyboard).hasSize(1);
        assertThat(storyboard.get(0).get("visualPrompt")).contains("纯音乐段落");

        // 历史测试运行可能在同名目录留下 subs.srt，先清掉再断言
        Path staleDir = Paths.get("./data/media/mv/" + song.getId());
        if (Files.exists(staleDir)) {
            try (var stream = Files.list(staleDir)) {
                for (Path p : (Iterable<Path>) stream::iterator) {
                    Files.deleteIfExists(p);
                }
            } catch (IOException ignored) {
            }
        }

        MvSong rendered = mvService.render(song.getId(), true);
        assertThat(rendered).isNotNull();

        Path mvDir = Paths.get("./data/media/mv/" + song.getId());
        Path finalMp4 = mvDir.resolve("final.mp4");
        Path subsSrt = mvDir.resolve("subs.srt");

        assertThat(finalMp4).exists();
        assertThat(subsSrt).doesNotExist();
    }

    @Test
    void importValidation() throws IOException {
        MockMultipartFile wav = buildWavFile();

        assertThatThrownBy(() -> mvService.importAudio(wav, "", "词", "m", "s"))
                .isInstanceOf(IllegalArgumentException.class);

        MockMultipartFile txt = new MockMultipartFile(
                "file", "song.txt", "text/plain", "hello".getBytes());
        assertThatThrownBy(() -> mvService.importAudio(txt, "标题", "词", "m", "s"))
                .isInstanceOf(IllegalArgumentException.class);

        MockMultipartFile empty = new MockMultipartFile(
                "file", "empty.wav", "audio/wav", new byte[0]);
        assertThatThrownBy(() -> mvService.importAudio(empty, "标题", "词", "m", "s"))
                .isInstanceOf(IllegalArgumentException.class);

        MultipartFile big = Mockito.mock(MultipartFile.class);
        Mockito.when(big.isEmpty()).thenReturn(false);
        Mockito.when(big.getSize()).thenReturn(101L * 1024 * 1024);
        Mockito.when(big.getOriginalFilename()).thenReturn("big.mp3");
        assertThatThrownBy(() -> mvService.importAudio(big, "标题", "词", "m", "s"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void importModeRejectsAiSteps() throws IOException {
        MockMultipartFile file = buildWavFile();
        MvSong song = mvService.importAudio(file, "测试歌曲", "第一句\n第二句", "mood", "style");
        CREATED_SONG_IDS.add(song.getId());
        assertThat(song).isNotNull();

        assertThatThrownBy(() -> mvService.generateLyrics(song.getId()))
                .isInstanceOf(IllegalStateException.class);

        assertThatThrownBy(() -> mvService.compose(song.getId(), 1L, "m"))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void buildLyricsJsonFromTextGrouping() {
        String json = mvService.buildLyricsJsonFromText("t", "a\nb\n\nc");
        assertThat(json).contains("段落 1");
        assertThat(json).contains("段落 2");

        assertThatThrownBy(() -> mvService.buildLyricsJsonFromText("t", ""))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
