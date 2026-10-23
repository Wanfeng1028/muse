package com.dramafactory.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "drama.storage=target/test-media-deconstruction-transcript")
@AutoConfigureMockMvc
class DeconstructionTranscriptApiTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    static Path videoPath = Paths.get("target/test-transcript-api/with-sub.mp4");

    @BeforeAll
    static void 准备带字幕视频() throws Exception {
        Path dir = videoPath.getParent();
        if (!Files.exists(dir)) {
            Files.createDirectories(dir);
        }

        Path srtPath = dir.resolve("sub.srt");
        String srtContent = "1\n" +
                "00:00:00,000 --> 00:00:02,000\n" +
                "你好，这是第一镜\n" +
                "\n" +
                "2\n" +
                "00:00:02,000 --> 00:00:04,000\n" +
                "第二镜的字幕内容\n" +
                "\n" +
                "3\n" +
                "00:00:04,000 --> 00:00:06,000\n" +
                "第三镜结束\n";
        Files.writeString(srtPath, srtContent);

        ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=10",
                "-i", srtPath.toAbsolutePath().toString(),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:s", "mov_text", "-shortest",
                videoPath.toAbsolutePath().toString()
        );
        pb.redirectErrorStream(true);
        Process process = pb.start();
        try (var is = process.getInputStream()) {
            is.transferTo(OutputStream.nullOutputStream());
        }
        boolean finished = process.waitFor(120, TimeUnit.SECONDS);
        assertTrue(finished, "ffmpeg 执行超时");
        assertEquals(0, process.exitValue(), "ffmpeg 执行失败");
    }

    @Test
    void transcriptFlow_带字幕全链路() throws Exception {
        // 1. 建项目
        String projectJson = objectMapper.writeValueAsString(
                java.util.Map.of("title", "逐字稿测试项目", "genre", "都市")
        );
        MvcResult projectResult = mockMvc.perform(post("/api/projects")
                        .contentType("application/json")
                        .content(projectJson))
                .andExpect(status().isCreated())
                .andReturn();
        JsonNode projectNode = objectMapper.readTree(projectResult.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8));
        long pid = projectNode.get("id").asLong();

        // 2. 上传带字幕视频
        byte[] videoBytes = Files.readAllBytes(videoPath);
        MockMultipartFile file = new MockMultipartFile("file", "with-sub.mp4", "video/mp4", videoBytes);

        MvcResult uploadResult = mockMvc.perform(multipart("/api/projects/{pid}/deconstructions/upload", pid)
                        .file(file))
                .andExpect(status().isCreated())
                .andReturn();
        JsonNode uploadNode = objectMapper.readTree(uploadResult.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8));
        long id = uploadNode.get("id").asLong();

        // 3. 轮询至 DONE
        JsonNode detail = null;
        for (int i = 0; i < 90; i++) {
            Thread.sleep(1000);
            MvcResult pollResult = mockMvc.perform(get("/api/projects/{pid}/deconstructions/{id}", pid, id))
                    .andExpect(status().isOk())
                    .andReturn();
            detail = objectMapper.readTree(pollResult.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8));
            String statusText = detail.get("status").asText();
            if ("DONE".equals(statusText)) {
                break;
            }
            if ("FAILED".equals(statusText)) {
                fail("拆解流水线失败");
            }
        }
        assertNotNull(detail, "未获取到拆解详情");
        assertEquals("DONE", detail.get("status").asText(), "拆解未完成");

        // 4. 断言逐字稿状态
        assertEquals("EMBEDDED", detail.get("transcriptStatus").asText(), "transcriptStatus 应为 EMBEDDED");

        // 5. 断言 transcriptSegments
        JsonNode segments = detail.get("transcriptSegments");
        assertTrue(segments.isArray(), "transcriptSegments 应为数组");
        assertEquals(3, segments.size(), "transcriptSegments 长度应为 3");
        assertEquals("你好，这是第一镜", segments.get(0).get("text").asText(), "第一条逐字稿文本不匹配");

        // 6. 断言 shots 的 transcriptText
        JsonNode shots = detail.get("shots");
        assertTrue(shots.isArray() && shots.size() > 0, "shots 应为非空数组");
        String transcriptText = shots.get(0).get("transcriptText").asText();
        assertFalse(transcriptText.isEmpty(), "第一个镜头的 transcriptText 不应为空");
        assertTrue(transcriptText.contains("你好"), "第一个镜头的 transcriptText 应包含'你好'");

        // 7. 获取报告并断言
        MvcResult reportResult = mockMvc.perform(get("/api/projects/{pid}/deconstructions/{id}/report", pid, id))
                .andExpect(status().isOk())
                .andReturn();
        String reportContent = reportResult.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8);
        assertTrue(reportContent.contains("逐字稿"), "报告应包含'逐字稿'");
        assertTrue(reportContent.contains("你好，这是第一镜"), "报告应包含'你好，这是第一镜'");
    }
}