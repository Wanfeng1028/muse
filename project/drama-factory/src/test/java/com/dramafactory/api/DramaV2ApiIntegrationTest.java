package com.dramafactory.api;

import com.dramafactory.service.VideoTaskService;
import com.dramafactory.service.video.MockVideoProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.fail;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * v2 API 集成测试。
 *
 * 说明：本测试环境的沙箱会拦截 JVM 的所有 TCP 连接（含 localhost），
 * 因此禁止使用 TestRestTemplate / 真实 HTTP，全部通过 MockMvc 驱动控制器层，
 * 并借助 videoTaskService.processDueTasks() 手动推进视频任务轮询，
 * 不依赖后台 @Scheduled 线程（默认每 10 秒跑一次）。
 */
@SpringBootTest
@AutoConfigureMockMvc
class DramaV2ApiIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private MockVideoProvider mockVideoProvider;

    @Autowired
    private VideoTaskService videoTaskService;

    @Test
    void testFullPipeline() throws Exception {
        // 1. 让 mock 视频提供者立即就绪，任务推进时可以直接进入 DONE。
        mockVideoProvider.setReadyAfterMs(0);

        // 2. 创建项目，取出项目 id。
        String projectBody = """
                {"title":"集成测试剧","genre":"测试"}
                """;
        String projectResp = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(projectBody))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").exists())
                .andReturn()
                .getResponse()
                .getContentAsString();
        long pid = objectMapper.readTree(projectResp).get("id").asLong();

        // 3. 在项目下创建第一集，取出剧集 id。
        String episodeBody = """
                {"episodeNo":1,"title":"第一集"}
                """;
        String episodeResp = mockMvc.perform(post("/api/projects/" + pid + "/episodes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(episodeBody))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").exists())
                .andReturn()
                .getResponse()
                .getContentAsString();
        long eid = objectMapper.readTree(episodeResp).get("id").asLong();

        // 4. 为该集创建两个分镜，记录分镜 id。
        String shot1Body = """
                {"shotNo":1,"shotSize":"ZHONG_JING","cameraMove":"GU_DING","description":"第一个分镜","dialogue":"你好","videoPrompt":"中景固定镜头","durationSeconds":2}
                """;
        String shot2Body = """
                {"shotNo":2,"shotSize":"ZHONG_JING","cameraMove":"GU_DING","description":"第二个分镜","dialogue":"再见","videoPrompt":"中景固定镜头","durationSeconds":2}
                """;
        String shot1Resp = mockMvc.perform(post("/api/episodes/" + eid + "/shots")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(shot1Body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").exists())
                .andReturn()
                .getResponse()
                .getContentAsString();
        long id1 = objectMapper.readTree(shot1Resp).get("id").asLong();

        String shot2Resp = mockMvc.perform(post("/api/episodes/" + eid + "/shots")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(shot2Body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").exists())
                .andReturn()
                .getResponse()
                .getContentAsString();
        long id2 = objectMapper.readTree(shot2Resp).get("id").asLong();

        // 5. 查询分镜列表，应有两个。
        mockMvc.perform(get("/api/episodes/" + eid + "/shots"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));

        // 6. 重排分镜，把第二个放到最前，再查询确认顺序。
        String reorderBody = objectMapper.writeValueAsString(
                java.util.Map.of("shotIds", java.util.List.of(id2, id1)));
        mockMvc.perform(post("/api/episodes/" + eid + "/shots/reorder")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(reorderBody))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/episodes/" + eid + "/shots"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(id2));

        // 7. 提交该集所有分镜的视频任务，应生成两个任务。
        mockMvc.perform(post("/api/episodes/" + eid + "/video-tasks/submit-all"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));

        // 8. 手动推进任务轮询，最多等待 60 秒，直到 id1 分镜下的所有任务都是 DONE。
        boolean allDone = false;
        long deadline = System.currentTimeMillis() + 60_000L;
        while (System.currentTimeMillis() < deadline) {
            videoTaskService.processDueTasks();

            String tasksResp = mockMvc.perform(get("/api/shots/" + id1 + "/video-tasks"))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getContentAsString();

            var tasks = objectMapper.readTree(tasksResp);
            boolean done = tasks.isArray() && tasks.size() > 0;
            for (var task : tasks) {
                if (!"DONE".equals(task.path("status").asText())) {
                    done = false;
                    break;
                }
            }
            if (done) {
                allDone = true;
                break;
            }
            Thread.sleep(1000L);
        }
        if (!allDone) {
            fail("视频任务未在 60 秒内全部变为 DONE");
        }

        // 9. 创建最终剪辑，应处于 READY。
        mockMvc.perform(post("/api/episodes/" + eid + "/final-cuts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("READY"));

        // 10. 查询项目流水线概览，校验集数、分镜数与已完成任务数。
        mockMvc.perform(get("/api/projects/" + pid + "/pipeline"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes.length()").value(1))
                .andExpect(jsonPath("$.episodes[0].shotCount").value(2))
                .andExpect(jsonPath("$.episodes[0].doneTasks").value(2));
    }
}
