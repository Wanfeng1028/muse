package com.dramafactory.api;

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.RunRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class RunLifecycleE2eTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private DramaProjectRepository dramaProjectRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private RunRepository runRepository;

    @Autowired
    private AgentStepRepository agentStepRepository;

    @Autowired
    private FinalCutRepository finalCutRepository;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private static final String USER_A = "e2e-a";
    private static final String USER_B = "e2e-b";

    private String createRunBody(String goal) {
        return "{\"goal\":\"" + goal + "\",\"plan\":{\"goal\":\"" + goal + "\",\"episodes\":[{\"episodeNo\":1,\"title\":\"第 1 集\",\"outline\":\"大纲\"}],\"fallback\":false}}";
    }

    private long createRun(String userId, String goal) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/runs")
                        .requestAttr("auth.userId", userId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createRunBody(goal)))
                .andExpect(status().isCreated())
                .andReturn();
        JsonNode node = objectMapper.readTree(result.getResponse().getContentAsString());
        return node.get("runId").asLong();
    }

    @Test
    void createRunAndPauseResumeCancel() throws Exception {
        // 建 run：断言 201 并拿到 runId
        long runId = createRun(USER_A, "全链路目标");

        // GET 详情：run 应为 RUNNING，步骤 5 个，seqNo 1..5，首个步骤名为 "第 1 集 · 编剧"
        mockMvc.perform(get("/api/runs/{id}", runId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.id").value((int) runId))
                .andExpect(jsonPath("$.run.status").value("RUNNING"))
                .andExpect(jsonPath("$.steps.length()").value(5))
                .andExpect(jsonPath("$.steps[0].seqNo").value(1))
                .andExpect(jsonPath("$.steps[1].seqNo").value(2))
                .andExpect(jsonPath("$.steps[2].seqNo").value(3))
                .andExpect(jsonPath("$.steps[3].seqNo").value(4))
                .andExpect(jsonPath("$.steps[4].seqNo").value(5))
                .andExpect(jsonPath("$.steps[0].name").value("第 1 集 · 编剧"));

        // pause → PAUSED
        mockMvc.perform(post("/api/runs/{id}/pause", runId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.status").value("PAUSED"));

        // 再次 pause → 非 RUNNING 状态，抛 IllegalStateException，全局异常处理器返回 409
        mockMvc.perform(post("/api/runs/{id}/pause", runId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isConflict());

        // resume → RUNNING
        mockMvc.perform(post("/api/runs/{id}/resume", runId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.status").value("RUNNING"));

        // cancel → CANCELLED
        mockMvc.perform(post("/api/runs/{id}/cancel", runId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.status").value("CANCELLED"));

        // GET 详情：5 个步骤 status 全为 CANCELLED
        mockMvc.perform(get("/api/runs/{id}", runId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.steps[0].status").value("CANCELLED"))
                .andExpect(jsonPath("$.steps[1].status").value("CANCELLED"))
                .andExpect(jsonPath("$.steps[2].status").value("CANCELLED"))
                .andExpect(jsonPath("$.steps[3].status").value("CANCELLED"))
                .andExpect(jsonPath("$.steps[4].status").value("CANCELLED"));
    }

    @Test
    void retryStepReopensRun() throws Exception {
        // 建 run 并 cancel，让 run 进入终态
        long runId = createRun(USER_A, "重试目标");
        mockMvc.perform(post("/api/runs/{id}/cancel", runId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk());

        // 取一个步骤 id
        MvcResult detail = mockMvc.perform(get("/api/runs/{id}", runId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode root = objectMapper.readTree(detail.getResponse().getContentAsString());
        long stepId = root.get("steps").get(0).get("id").asLong();

        // retry：步骤回 PENDING，run 重开为 RUNNING
        mockMvc.perform(post("/api/runs/{id}/steps/{stepId}/retry", runId, stepId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.steps[0].status").value("PENDING"))
                .andExpect(jsonPath("$.run.status").value("RUNNING"));
    }

    @Test
    void rerunFromTerminal() throws Exception {
        // 先建一个 run 并 cancel 成终态
        long oldRunId = createRun(USER_A, "重跑目标");
        mockMvc.perform(post("/api/runs/{id}/cancel", oldRunId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk());

        // 对终态 run 调 rerun → 201，新 runId ≠ 旧
        MvcResult rerunResult = mockMvc.perform(post("/api/runs/{id}/rerun", oldRunId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isCreated())
                .andReturn();
        JsonNode rerunNode = objectMapper.readTree(rerunResult.getResponse().getContentAsString());
        long newRunId = rerunNode.get("runId").asLong();
        assertThat(newRunId).isNotEqualTo(oldRunId);

        // GET 新 run：RUNNING 且有 5 个步骤
        mockMvc.perform(get("/api/runs/{id}", newRunId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.status").value("RUNNING"))
                .andExpect(jsonPath("$.steps.length()").value(5));

        // 对 RUNNING 的 run 调 rerun → 409
        mockMvc.perform(post("/api/runs/{id}/rerun", newRunId)
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isConflict());
    }

    @Test
    void approveAccepted() throws Exception {
        // 直接建实体：项目、集、WAITING_APPROVAL 的 run、RUNNING 的 QC 步骤、READY 成片
        DramaProject project = new DramaProject();
        project.setTitle("审批项目");
        project.setOwnerId("local");
        project = dramaProjectRepository.save(project);

        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode.setTitle("第 1 集");
        episode = episodeRepository.save(episode);

        Run run = new Run();
        run.setGoal("审批目标");
        run.setStatus(RunStatus.WAITING_APPROVAL);
        run.setProjectId(project.getId());
        run = runRepository.save(run);

        AgentStep qcStep = new AgentStep();
        qcStep.setRun(run);
        qcStep.setSeqNo(1);
        qcStep.setAgentType(AgentType.QC);
        qcStep.setName("第 1 集 · 质检");
        qcStep.setStatus(AgentStepStatus.RUNNING);
        qcStep.setEpisodeId(episode.getId());
        qcStep = agentStepRepository.save(qcStep);

        FinalCut finalCut = new FinalCut();
        finalCut.setEpisode(episode);
        finalCut.setTitle("成片");
        finalCut.setFilePath("/tmp/x.mp4");
        finalCut.setStatus(FinalCutStatus.READY);
        finalCutRepository.save(finalCut);

        // approve 通过 → 200，run 回 RUNNING，QC 步骤 SUCCEEDED
        mockMvc.perform(post("/api/runs/{id}/approve", run.getId())
                        .requestAttr("auth.userId", "local")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"approved\":true,\"note\":\"通过\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.status").value("RUNNING"))
                .andExpect(jsonPath("$.steps[0].status").value("SUCCEEDED"));
    }

    @Test
    void approveRejected() throws Exception {
        // 同上建实体，QC 步骤 RUNNING，成片 READY
        DramaProject project = new DramaProject();
        project.setTitle("拒绝项目");
        project.setOwnerId("local");
        project = dramaProjectRepository.save(project);

        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode.setTitle("第 1 集");
        episode = episodeRepository.save(episode);

        Run run = new Run();
        run.setGoal("拒绝目标");
        run.setStatus(RunStatus.WAITING_APPROVAL);
        run.setProjectId(project.getId());
        run = runRepository.save(run);

        AgentStep qcStep = new AgentStep();
        qcStep.setRun(run);
        qcStep.setSeqNo(1);
        qcStep.setAgentType(AgentType.QC);
        qcStep.setName("第 1 集 · 质检");
        qcStep.setStatus(AgentStepStatus.RUNNING);
        qcStep.setEpisodeId(episode.getId());
        qcStep = agentStepRepository.save(qcStep);

        FinalCut finalCut = new FinalCut();
        finalCut.setEpisode(episode);
        finalCut.setTitle("成片");
        finalCut.setFilePath("/tmp/x.mp4");
        finalCut.setStatus(FinalCutStatus.READY);
        finalCutRepository.save(finalCut);

        // approve 拒绝 → run FAILED，QC 步骤 FAILED 且 errorMessage="不行"
        mockMvc.perform(post("/api/runs/{id}/approve", run.getId())
                        .requestAttr("auth.userId", "local")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"approved\":false,\"note\":\"不行\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.status").value("FAILED"))
                .andExpect(jsonPath("$.steps[0].status").value("FAILED"))
                .andExpect(jsonPath("$.steps[0].errorMessage").value("不行"));
    }

    @Test
    void runStatsIsolatedByUser() throws Exception {
        // 用 e2e-a 建一个 run，e2e-b 不建，只断言两个用户的口径隔离
        createRun(USER_A, "统计目标");

        mockMvc.perform(get("/api/runs/stats")
                        .requestAttr("auth.userId", USER_A))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalRuns").value(1));

        mockMvc.perform(get("/api/runs/stats")
                        .requestAttr("auth.userId", USER_B))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalRuns").value(0));
    }
}
