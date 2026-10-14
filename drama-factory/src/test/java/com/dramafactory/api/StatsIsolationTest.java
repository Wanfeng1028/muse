
package com.dramafactory.api;

import com.dramafactory.model.DramaCharacter;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.Scene;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.SceneRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class StatsIsolationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaCharacterRepository characterRepository;

    @Autowired
    private SceneRepository sceneRepository;

    @Autowired
    private RunRepository runRepository;

    @Test
    void projectStatsAreIsolatedByCurrentUser() throws Exception {
        // local 口径基线：其他非事务测试类（如 DramaV2ApiIntegrationTest）可能已在共享 H2 库里留下 local 数据，
        // 因此不断言绝对值，只断言本测试创建的数据不会污染 local 口径
        int localProjectsBefore = projectsOf(null);

        DramaProject aProject = new DramaProject();
        aProject.setTitle("A项目");
        aProject.setOwnerId("user-a");
        aProject = projectRepository.save(aProject);

        Episode aEpisode = new Episode();
        aEpisode.setProject(aProject);
        aEpisode.setEpisodeNo(1);
        aEpisode.setTitle("第 1 集");
        aEpisode = episodeRepository.save(aEpisode);

        DramaCharacter aCharacter = new DramaCharacter();
        aCharacter.setProject(aProject);
        aCharacter.setName("角色甲");
        characterRepository.save(aCharacter);

        Scene aScene = new Scene();
        aScene.setEpisode(aEpisode);
        aScene.setSceneNo(1);
        aScene.setLocation("客厅");
        sceneRepository.save(aScene);

        DramaProject bProject = new DramaProject();
        bProject.setTitle("B项目");
        bProject.setOwnerId("user-b");
        projectRepository.save(bProject);

        mockMvc.perform(get("/api/stats").requestAttr("auth.userId", "user-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projects").value(1))
                .andExpect(jsonPath("$.episodes").value(1))
                .andExpect(jsonPath("$.characters").value(1))
                .andExpect(jsonPath("$.scenes").value(1));

        mockMvc.perform(get("/api/stats").requestAttr("auth.userId", "user-b"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projects").value(1))
                .andExpect(jsonPath("$.episodes").value(0));

        mockMvc.perform(get("/api/stats"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projects").value(localProjectsBefore));
    }

    /** 查某用户口径的 projects 数：userId 为 null 时走 local 口径。 */
    private int projectsOf(String userId) throws Exception {
        var req = get("/api/stats");
        if (userId != null) {
            req.requestAttr("auth.userId", userId);
        }
        String body = mockMvc.perform(req)
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        // 简单解析 "projects":N
        String marker = "\"projects\":";
        int idx = body.indexOf(marker);
        if (idx < 0) {
            throw new IllegalStateException("响应中没有 projects 字段: " + body);
        }
        int start = idx + marker.length();
        int end = start;
        while (end < body.length() && Character.isDigit(body.charAt(end))) {
            end++;
        }
        return Integer.parseInt(body.substring(start, end));
    }

    @Test
    void runStatsAreIsolatedByCurrentUser() throws Exception {
        DramaProject aProject = new DramaProject();
        aProject.setTitle("A项目");
        aProject.setOwnerId("user-a");
        aProject = projectRepository.save(aProject);

        Run aRun = new Run();
        aRun.setGoal("跑一遍");
        aRun.setProjectId(aProject.getId());
        aRun.setStatus(RunStatus.SUCCEEDED);
        runRepository.save(aRun);

        DramaProject bProject = new DramaProject();
        bProject.setTitle("B项目");
        bProject.setOwnerId("user-b");
        projectRepository.save(bProject);

        mockMvc.perform(get("/api/runs/stats").requestAttr("auth.userId", "user-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalRuns").value(1))
                .andExpect(jsonPath("$.succeeded").value(1));

        mockMvc.perform(get("/api/runs/stats").requestAttr("auth.userId", "user-b"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalRuns").value(0));
    }
}
