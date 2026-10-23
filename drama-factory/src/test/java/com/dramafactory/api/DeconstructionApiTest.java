package com.dramafactory.api;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "drama.storage=target/test-media-deconstruction")
@AutoConfigureMockMvc
class DeconstructionApiTest {

    static Path VIDEO_FILE;
    @Autowired
    private MockMvc mockMvc;
    @Autowired
    private ObjectMapper objectMapper;

    @BeforeAll
    static void makeVideo() throws Exception {
        Path targetDir = Paths.get("target/test-media-deconstruction-src");
        Files.createDirectories(targetDir);
        VIDEO_FILE = targetDir.resolve("sample.mp4");
        if (!Files.exists(VIDEO_FILE)) {
            ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg",
                "-y",
                "-f", "lavfi", "-i", "color=c=white:s=320x240:r=25:d=2",
                "-f", "lavfi", "-i", "color=c=red:s=320x240:r=25:d=2",
                "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=2",
                "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
                "-map", "[v]",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                VIDEO_FILE.toString()
            );
            pb.redirectErrorStream(true);
            Process process = pb.start();
            assertTrue(process.waitFor(120, TimeUnit.SECONDS), "ffmpeg process timeout");
            assertEquals(0, process.exitValue(), "ffmpeg process failed");
            assertTrue(Files.exists(VIDEO_FILE), "video file not created");
            assertTrue(Files.size(VIDEO_FILE) > 3000, "video file too small");
        }
    }

    private long createProject() throws Exception {
        String projectJson = "{\"title\":\"拆解测试项目\",\"genre\":\"都市\"}";
        MvcResult result = mockMvc.perform(post("/api/projects")
                .contentType(MediaType.APPLICATION_JSON)
                .content(projectJson))
            .andExpect(status().isCreated())
            .andReturn();
        JsonNode response = objectMapper.readTree(result.getResponse().getContentAsString());
        return response.get("id").asLong();
    }

    private long createEpisode(long pid) throws Exception {
        String episodeJson = "{\"episodeNo\":1,\"title\":\"第一集\"}";
        MvcResult result = mockMvc.perform(post("/api/projects/" + pid + "/episodes")
                .contentType(MediaType.APPLICATION_JSON)
                .content(episodeJson))
            .andExpect(status().isCreated())
            .andReturn();
        JsonNode response = objectMapper.readTree(result.getResponse().getContentAsString());
        return response.get("id").asLong();
    }

    private JsonNode awaitDone(long pid, long id) throws Exception {
        for (int i = 0; i < 90; i++) {
            MvcResult result = mockMvc.perform(get("/api/projects/" + pid + "/deconstructions/" + id))
                .andExpect(status().isOk())
                .andReturn();
            JsonNode detail = objectMapper.readTree(result.getResponse().getContentAsString());
            String status = detail.get("status").asText();
            if ("DONE".equals(status)) {
                return detail;
            } else if ("FAILED".equals(status)) {
                String errorMsg = detail.has("errorMessage") ? detail.get("errorMessage").asText() : "未知错误";
                fail("拆解失败：" + errorMsg);
            }
            Thread.sleep(1000);
        }
        fail("拆解未在 90 秒内完成");
        return null;
    }

    @Test
    void uploadAnalyzeReportGenerateShotsFlow() throws Exception {
        // 1. 创建项目和剧集
        long pid = createProject();
        long eid = createEpisode(pid);
        
        // 2. 上传视频进行拆解
        MockMultipartFile file = new MockMultipartFile(
            "file", "sample.mp4", "video/mp4", 
            Files.readAllBytes(VIDEO_FILE)
        );
        MvcResult uploadResult = mockMvc.perform(multipart("/api/projects/" + pid + "/deconstructions/upload")
                .file(file))
            .andExpect(status().isCreated())
            .andReturn();
        JsonNode uploadResponse = objectMapper.readTree(uploadResult.getResponse().getContentAsString());
        long id = uploadResponse.get("id").asLong();
        String status = uploadResponse.get("status").asText();
        assertTrue("PENDING".equals(status) || "RUNNING".equals(status), 
            "初始状态应为 PENDING 或 RUNNING，实际: " + status);
        
        // 3. 等待拆解完成并验证结果
        JsonNode detail = awaitDone(pid, id);
        int shotCount = detail.get("shotCount").asInt();
        assertTrue(shotCount >= 3, "镜头数量应>=3，实际: " + shotCount);
        JsonNode shots = detail.get("shots");
        assertEquals(shotCount, shots.size(), "镜头数组大小应等于shotCount");
        assertNotNull(shots.get(0).get("keyframeUrl"), "第一个镜头的keyframeUrl不应为null");
        
        // 4. 验证关键帧图片
        String keyframeUrl = shots.get(0).get("keyframeUrl").asText();
        mockMvc.perform(get(keyframeUrl))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.IMAGE_JPEG))
            .andExpect(res -> assertTrue(
                res.getResponse().getContentAsByteArray().length > 500,
                "关键帧图片大小应>500字节"
            ));
        
        // 5. 获取拆解报告
        mockMvc.perform(get("/api/projects/" + pid + "/deconstructions/" + id + "/report"))
            .andExpect(status().isOk())
            .andExpect(res -> {
                String reportContent = res.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8);
                assertTrue(reportContent.contains("视频拆解报告"));
                assertTrue(reportContent.contains("逐镜表"));
                assertTrue(reportContent.contains("Seedance 版"));
                assertTrue(reportContent.contains("数据口径说明"));
            });
        
        // 6. 生成镜头并验证
        MvcResult generateResult = mockMvc.perform(post("/api/projects/" + pid + "/deconstructions/" + id + "/generate-shots")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"episodeId\": " + eid + "}"))
            .andExpect(status().isCreated())
            .andReturn();
        JsonNode generateResponse = objectMapper.readTree(generateResult.getResponse().getContentAsString());
        int createdCount = generateResponse.get("createdCount").asInt();
        assertEquals(shotCount, createdCount, "生成的镜头数量应等于拆解镜头数量");
        
        mockMvc.perform(get("/api/episodes/" + eid + "/shots"))
            .andExpect(status().isOk())
            .andExpect(res -> {
                JsonNode shotsArray = objectMapper.readTree(res.getResponse().getContentAsString());
                assertEquals(shotCount, shotsArray.size(), "剧集镜头数量应等于拆解镜头数量");
            });
        
        // 7. 删除拆解记录
        mockMvc.perform(delete("/api/projects/" + pid + "/deconstructions/" + id))
            .andExpect(status().isNoContent());
        mockMvc.perform(get("/api/projects/" + pid + "/deconstructions/" + id))
            .andExpect(status().isNotFound());
    }
}
