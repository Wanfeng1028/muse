package com.dramafactory.controller;

import com.dramafactory.service.MvLyricsService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * /api/mv/import 控制器集成测试。
 */
@SpringBootTest
@AutoConfigureMockMvc
class MvImportControllerTest {

    private static final Path TEST_AUDIO_DIR = Paths.get("./data/media/import-test");
    private static final Path TEST_WAV = TEST_AUDIO_DIR.resolve("import-controller-test.wav");

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private MvLyricsService mvLyricsService;

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
        assertThat(exit).as("ffmpeg 生成测试音频应成功").isZero();
        assertThat(TEST_WAV).exists();
        assertThat(Files.size(TEST_WAV)).isGreaterThan(0L);
    }

    private MockMultipartFile buildWavFile() throws IOException {
        byte[] bytes = Files.readAllBytes(TEST_WAV);
        return new MockMultipartFile("file", "song.wav", "audio/wav", bytes);
    }

    @Test
    void importValidReturns200() throws Exception {
        MockMultipartFile file = buildWavFile();

        String responseBody = mockMvc.perform(multipart("/api/mv/import")
                        .file(file)
                        .param("title", "控制器测试")
                        .param("lyrics", "第一句\n第二句")
                        .param("mood", "happy")
                        .param("style", "pop"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.id").exists())
                .andExpect(jsonPath("$.audioUrl").exists())
                .andReturn()
                .getResponse()
                .getContentAsString();

        assertThat(responseBody).contains("/api/assets/");

        Object idObj = com.jayway.jsonpath.JsonPath.read(responseBody, "$.id");
        long id = ((Number) idObj).longValue();

        mockMvc.perform(get("/api/mv/" + id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.source").value("IMPORT"));
    }

    @Test
    void importBadExtensionReturns400() throws Exception {
        MockMultipartFile txt = new MockMultipartFile(
                "file", "song.txt", "text/plain", "hello".getBytes());

        mockMvc.perform(multipart("/api/mv/import")
                        .file(txt)
                        .param("title", "标题")
                        .param("mood", "m")
                        .param("style", "s"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void importMissingTitleReturns400() throws Exception {
        MockMultipartFile file = buildWavFile();

        mockMvc.perform(multipart("/api/mv/import")
                        .file(file)
                        .param("mood", "m")
                        .param("style", "s"))
                .andExpect(status().isBadRequest());
    }
}
