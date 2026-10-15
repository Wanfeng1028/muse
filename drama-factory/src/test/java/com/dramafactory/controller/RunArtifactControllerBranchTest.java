package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.Scene;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.config.JwtVerifier;
import com.dramafactory.service.RunService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RunArtifactController.class)
class RunArtifactControllerBranchTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private JwtVerifier jwtVerifier;

    @MockBean
    private RunService runService;

    @MockBean
    private EpisodeRepository episodeRepository;

    @MockBean
    private SceneRepository sceneRepository;

    @MockBean
    private ShotRepository shotRepository;

    @MockBean
    private VideoTaskRepository videoTaskRepository;

    @MockBean
    private FinalCutRepository finalCutRepository;

    private Records.RunResponse runResponse() {
        return new Records.RunResponse(1L, "测试", RunStatus.RUNNING, "执行中", 7L, null, null,
                LocalDateTime.now(), LocalDateTime.now());
    }

    private Episode ep1() {
        Episode e1 = new Episode();
        e1.setId(10L);
        e1.setEpisodeNo(1);
        e1.setTitle("第一集");
        return e1;
    }

    private Episode ep2() {
        Episode e2 = new Episode();
        e2.setId(20L);
        e2.setEpisodeNo(2);
        e2.setTitle("第二集");
        return e2;
    }

    private Scene s1() {
        Scene s1 = new Scene();
        s1.setSceneNo(1);
        s1.setLocation("客厅");
        s1.setDescription("争吵");
        s1.setDialogue("你走吧");
        return s1;
    }

    private Scene s2Nulls() {
        Scene s2 = new Scene();
        s2.setSceneNo(2);
        return s2;
    }

    private Scene s3Blank() {
        Scene s3 = new Scene();
        s3.setSceneNo(3);
        s3.setLocation("厨房");
        s3.setDescription("沉默");
        s3.setDialogue(" ");
        return s3;
    }

    private Shot sh1() {
        Shot sh1 = new Shot();
        sh1.setId(100L);
        sh1.setShotNo(1);
        sh1.setDescription("特写");
        sh1.setDurationSeconds(5);
        return sh1;
    }

    private Shot sh2() {
        Shot sh2 = new Shot();
        sh2.setId(101L);
        sh2.setShotNo(2);
        sh2.setShotSize(ShotSize.TE_XIE);
        sh2.setCameraMove(CameraMove.TUI);
        return sh2;
    }

    private VideoTask t1() {
        VideoTask t1 = new VideoTask();
        t1.setId(1000L);
        t1.setShot(sh1());
        t1.setProvider("agnes");
        t1.setModelUsed("m1");
        t1.setStatus(VideoTaskStatus.DONE);
        t1.setCostCents(50L);
        return t1;
    }

    private VideoTask t2() {
        VideoTask t2 = new VideoTask();
        t2.setId(1001L);
        t2.setShot(sh1());
        return t2;
    }

    private FinalCut fc1() {
        FinalCut fc1 = new FinalCut();
        fc1.setId(2000L);
        fc1.setFilePath("/f/a.mp4");
        fc1.setStatus(FinalCutStatus.READY);
        fc1.setQcStatus("PASS");
        fc1.setQcNote("ok");
        fc1.setDurationSeconds(60.5);
        return fc1;
    }

    private FinalCut fc2() {
        FinalCut fc2 = new FinalCut();
        fc2.setId(2001L);
        return fc2;
    }

    private void stubRun() {
        when(runService.getRun(1L)).thenReturn(new Records.RunDetailResponse(runResponse(), List.of(), 7L));
    }

    // 覆盖 L65-79 主路径 + L76(m2c0) episodes 循环两次；ep1 有数据、ep2 全空 → 断言 episodes 长度 2
    @Test
    void branch_twoEpisodesIteratedWithFullAndEmptyArtifacts() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1(), ep2()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of(s1(), s2Nulls()));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of(sh1(), sh2()));
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>(List.of(t2(), t1())));
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of(fc1(), fc2()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(20L)).thenReturn(List.of());
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(20L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(20L)).thenReturn(new ArrayList<>());
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(20L)).thenReturn(List.of());

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId").value(1))
                .andExpect(jsonPath("$.episodes.length()").value(2))
                .andExpect(jsonPath("$.episodes[0].episodeId").value(10))
                .andExpect(jsonPath("$.episodes[0].episodeNo").value(1))
                .andExpect(jsonPath("$.episodes[0].title").value("第一集"))
                .andExpect(jsonPath("$.episodes[1].episodeId").value(20))
                .andExpect(jsonPath("$.episodes[1].episodeNo").value(2))
                .andExpect(jsonPath("$.episodes[1].title").value("第二集"))
                .andExpect(jsonPath("$.episodes[1].scriptText").value(""))
                .andExpect(jsonPath("$.episodes[1].shots.length()").value(0))
                .andExpect(jsonPath("$.episodes[1].videos.length()").value(0))
                .andExpect(jsonPath("$.episodes[1].finalCuts.length()").value(0));
    }

    // 覆盖 L110/111(m2c0) scenes 循环 + sb.length()>0 换行；ep1 两场，第二场以 \n 开头
    @Test
    void branch_scriptTextNewlineBetweenScenes() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of(s1(), s2Nulls()));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>());
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of());

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes[0].scriptText")
                        .value(org.hamcrest.Matchers.containsString("【第1场·客厅】争吵\n台词：你走吧\n【第2场·】")));
    }

    // 覆盖 L115(m2c0) location null 三元 + L116(m2c0) description null 三元 → 第二场 "【第2场·】" 后无描述
    @Test
    void branch_scriptTextNullLocationAndDescription() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of(s2Nulls()));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>());
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of());

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes[0].scriptText").value("【第2场·】"))
                .andExpect(jsonPath("$.episodes[0].scriptText")
                        .value(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("null"))));
    }

    // 覆盖 L117(m4c0) dialogue 三分支：非空走"台词："；null 无行；空白无行
    @Test
    void branch_scriptTextDialogueThreeBranches() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of(s1(), s2Nulls(), s3Blank()));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>());
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of());

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes[0].scriptText")
                        .value("【第1场·客厅】争吵\n台词：你走吧\n【第2场·】\n【第3场·厨房】沉默"))
                .andExpect(jsonPath("$.episodes[0].scriptText")
                        .value(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("台词： "))));
    }

    // 覆盖 L133(m2c0) shots 循环两次 → 断言 shots 长度 2
    @Test
    void branch_shotsLoopProducesTwoArtifacts() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of());
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of(sh1(), sh2()));
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>());
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of());

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes[0].shots.length()").value(2))
                .andExpect(jsonPath("$.episodes[0].shots[0].id").value(100))
                .andExpect(jsonPath("$.episodes[0].shots[1].id").value(101));
    }

    // 覆盖 L137/138(m2c0) shotSize/cameraMove null 三元：sh1 全 null，sh2 为 "TE_XIE"/"TUI"
    @Test
    void branch_shotSizeAndCameraMoveNullTernary() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of());
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of(sh1(), sh2()));
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>());
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of());

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes[0].shots[0].shotSize").doesNotExist())
                .andExpect(jsonPath("$.episodes[0].shots[0].cameraMove").doesNotExist())
                .andExpect(jsonPath("$.episodes[0].shots[1].shotSize").value("TE_XIE"))
                .andExpect(jsonPath("$.episodes[0].shots[1].cameraMove").value("TUI"));
    }

    // 覆盖 L156/157(m2c0) videos 循环 + status null 三元，并验证 controller 内按 id 升序排序
    @Test
    void branch_videosSortedByIdAndStatusNullTernary() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of());
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>(List.of(t2(), t1())));
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of());

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes[0].videos.length()").value(2))
                .andExpect(jsonPath("$.episodes[0].videos[0].taskId").value(1000))
                .andExpect(jsonPath("$.episodes[0].videos[0].status").value("DONE"))
                .andExpect(jsonPath("$.episodes[0].videos[0].statusLabel").value("DONE"))
                .andExpect(jsonPath("$.episodes[0].videos[0].url").value("/media/videos/1000"))
                .andExpect(jsonPath("$.episodes[0].videos[1].taskId").value(1001))
                .andExpect(jsonPath("$.episodes[0].videos[1].status").doesNotExist())
                .andExpect(jsonPath("$.episodes[0].videos[1].statusLabel").doesNotExist())
                .andExpect(jsonPath("$.episodes[0].videos[1].url").value("/media/videos/1001"));
    }

    // 覆盖 L181(m2c0) finalCuts 循环两次 → 断言 finalCuts 长度 2 及 url 规则
    @Test
    void branch_finalCutsLoopProducesTwoArtifacts() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of());
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>());
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of(fc1(), fc2()));

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes[0].finalCuts.length()").value(2))
                .andExpect(jsonPath("$.episodes[0].finalCuts[0].id").value(2000))
                .andExpect(jsonPath("$.episodes[0].finalCuts[0].url").value("/media/finals/2000"))
                .andExpect(jsonPath("$.episodes[0].finalCuts[1].id").value(2001))
                .andExpect(jsonPath("$.episodes[0].finalCuts[1].url").value("/media/finals/2001"));
    }

    // 覆盖 L186(m2c0) cut status null 三元：fc1 "READY" 且 qc 字段透传；fc2 status 为 JSON null
    @Test
    void branch_finalCutStatusNullTernary() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of(ep1()));
        when(sceneRepository.findByEpisodeIdOrderBySceneNoAsc(10L)).thenReturn(List.of());
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(new ArrayList<>());
        when(finalCutRepository.findByEpisodeIdOrderByIdDesc(10L)).thenReturn(List.of(fc1(), fc2()));

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodes[0].finalCuts[0].status").value("READY"))
                .andExpect(jsonPath("$.episodes[0].finalCuts[0].qcStatus").value("PASS"))
                .andExpect(jsonPath("$.episodes[0].finalCuts[0].qcNote").value("ok"))
                .andExpect(jsonPath("$.episodes[0].finalCuts[0].durationSeconds").value(60.5))
                .andExpect(jsonPath("$.episodes[0].finalCuts[1].status").doesNotExist())
                .andExpect(jsonPath("$.episodes[0].finalCuts[1].qcStatus").doesNotExist());
    }

    // 覆盖 L73-79 空分支：episodeRepository 返回空 → episodes 为 []
    @Test
    void branch_noEpisodesReturnsEmptyArray() throws Exception {
        stubRun();
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(7L)).thenReturn(List.of());

        mockMvc.perform(get("/api/runs/1/artifacts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId").value(1))
                .andExpect(jsonPath("$.episodes.length()").value(0));
    }
}
