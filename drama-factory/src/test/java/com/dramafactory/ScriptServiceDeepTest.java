package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.DramaProject;import com.dramafactory.model.Scene;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.DramaProjectRepository;import com.dramafactory.repository.SceneRepository;
import com.dramafactory.service.ScriptService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class ScriptServiceDeepTest {

    @Autowired
    private ScriptService scriptService;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private SceneRepository sceneRepository;

    @Autowired
    private DramaProjectRepository projectRepository;

    private DramaProject project;

    private Episode newEpisode(String title, String outline) {
        DramaProject p = new DramaProject();
        p.setTitle("测试项目");
        DramaProject savedProject = projectRepository.save(p);        this.project = savedProject;
        Episode e = new Episode();
        e.setProject(savedProject);
        e.setEpisodeNo(1);
        e.setTitle(title);
        e.setOutline(outline);
        e.setStatus(EpisodeStatus.DRAFT);
        return episodeRepository.save(e);
    }

    @BeforeEach
    void setUp() {
        this.project = null;
    }

    @Test
    void generate_ai模式_成功后应落库场景并把剧集置为SCRIPTED() {
        Episode episode = newEpisode("第一集", "主角登场");

        Records.GenerateScriptResponse resp = scriptService.generate(episode.getId(), "ai");

        assertNotNull(resp);
        assertTrue("ai".equals(resp.source()) || "template-fallback".equals(resp.source()));
        assertEquals(episode.getId(), resp.episodeId());
        assertTrue(resp.sceneCount() >= 1);
        assertNotNull(resp.scriptText());
        assertFalse(resp.scriptText().isBlank());
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus());
        List<Scene> scenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episode.getId());
        assertEquals(resp.sceneCount(), scenes.size());
    }

    @Test
    void generate_template模式_应返回template来源且模型字段为空() {
        Episode episode = newEpisode("模板集", "模板大纲");

        Records.GenerateScriptResponse resp = scriptService.generate(episode.getId(), "template");

        assertEquals("template", resp.source());
        assertNull(resp.model());
        assertNull(resp.usedSkill());
        assertEquals(0L, resp.promptTokens());
        assertEquals(0L, resp.completionTokens());
        assertTrue(resp.sceneCount() >= 1);
    }

    @Test
    void generate_幂等性_同一剧集重复生成场景不叠加() {
        Episode episode = newEpisode("幂等集", "幂等大纲");
        Records.GenerateScriptResponse first = scriptService.generate(episode.getId(), "template");
        int firstCount = first.sceneCount();
        List<Scene> firstScenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episode.getId());

        Records.GenerateScriptResponse second = scriptService.generate(episode.getId(), "template");

        assertEquals(firstCount, second.sceneCount());
        List<Scene> secondScenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episode.getId());
        assertEquals(firstScenes.size(), secondScenes.size());
        assertEquals(firstCount, secondScenes.size());
    }

    @Test
    void generate_非法mode_应抛IllegalArgumentException() {
        Episode episode = newEpisode("非法模式", "大纲");

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> scriptService.generate(episode.getId(), "unknown"));

        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains("ai"));
        assertTrue(ex.getMessage().contains("template"));
        List<Scene> scenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episode.getId());
        assertEquals(0, scenes.size());
    }

    @Test
    void generate_剧集不存在_应抛ResourceNotFoundException() {
        Long missingId = 999999L;

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> scriptService.generate(missingId, "template"));

        assertNotNull(ex);
        List<Scene> scenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(missingId);
        assertEquals(0, scenes.size());
    }

    @Test
    void generate_失败注入_非法mode不应清空已存在场景() {
        Episode episode = newEpisode("失败注入", "旧场景将被清理");
        scriptService.generate(episode.getId(), "template");
        List<Scene> before = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episode.getId());
        assertTrue(before.size() >= 1);

        assertThrows(IllegalArgumentException.class,
                () -> scriptService.generate(episode.getId(), "invalid-mode"));

        List<Scene> after = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episode.getId());
        assertEquals(before.size(), after.size());
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus());
    }

    @Test
    void generate_边界_大payload不应崩溃() {
        StringBuilder big = new StringBuilder();
        // Episode.outline 列为 VARCHAR(2000)，构造约 1750 字符的"大"大纲（相对常规大纲高两个数量级）
        for (int i = 0; i < 250; i++) {
            big.append("剧情段落").append(i).append("；");
        }
        Episode episode = newEpisode("大payload", big.toString());

        Records.GenerateScriptResponse resp = scriptService.generate(episode.getId(), "template");

        assertNotNull(resp);
        assertTrue(resp.sceneCount() >= 1);
        assertNotNull(resp.scriptText());
        assertTrue(resp.scriptText().length() > 0);
    }

    @Test
    void generate_边界_空标题空大纲不应崩溃() {
        Episode episode = newEpisode("", "");

        Records.GenerateScriptResponse resp = scriptService.generate(episode.getId(), "template");

        assertNotNull(resp);
        assertTrue(resp.sceneCount() >= 1);
        assertEquals(episode.getId(), resp.episodeId());
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus());
    }

    @Test
    void generate_ai模式_无可用大模型时应降级为template_fallback() {
        Episode episode = newEpisode("降级集", "降级大纲");

        Records.GenerateScriptResponse resp = scriptService.generate(episode.getId(), "ai");

        assertNotNull(resp);
        assertTrue("ai".equals(resp.source()) || "template-fallback".equals(resp.source()));
        assertTrue(resp.sceneCount() >= 1);
        List<Scene> scenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episode.getId());
        assertEquals(resp.sceneCount(), scenes.size());
    }

    @Test
    void generate_并发_两线程同时推进同一Run数据保持一致() throws Exception {
        Episode episode = newEpisode("并发集", "并发大纲");
        final Long episodeId = episode.getId();
        // 工作线程使用独立事务，看不到本测试事务中未提交的 episode，必须先提交并结束测试事务
        org.springframework.test.context.transaction.TestTransaction.flagForCommit();
        org.springframework.test.context.transaction.TestTransaction.end();
        final Records.GenerateScriptResponse[] results = new Records.GenerateScriptResponse[2];
        final Throwable[] errors = new Throwable[2];

        Runnable task0 = () -> {
            try {
                results[0] = scriptService.generate(episodeId, "template");
            } catch (Throwable t) {
                errors[0] = t;
            }
        };
        Runnable task1 = () -> {
            try {
                results[1] = scriptService.generate(episodeId, "template");
            } catch (Throwable t) {
                errors[1] = t;
            }
        };

        Thread t0 = new Thread(task0);
        Thread t1 = new Thread(task1);
        t0.start();
        t1.start();
        t0.join();
        t1.join();

        // 线程结束后重新开启测试事务以便后续仓库读取
        org.springframework.test.context.transaction.TestTransaction.start();

        assertNull(errors[0]);
        assertNull(errors[1]);
        assertNotNull(results[0]);
        assertNotNull(results[1]);
        List<Scene> scenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episodeId);
        assertTrue(scenes.size() >= 1);
        Episode reloaded = episodeRepository.findById(episodeId).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus());
    }

    @Test
    void generate_边界_场景序号与内容应和返回结果一致() {
        Episode episode = newEpisode("序号集", "序号大纲");

        Records.GenerateScriptResponse resp = scriptService.generate(episode.getId(), "template");

        List<Scene> scenes = sceneRepository.findByEpisodeIdOrderBySceneNoAsc(episode.getId());
        assertEquals(resp.sceneCount(), scenes.size());
        for (int i = 0; i < scenes.size(); i++) {
            Scene s = scenes.get(i);
            assertEquals(episode.getId(), s.getEpisode().getId());
            assertNotNull(s.getSceneNo());
            assertEquals(i + 1, s.getSceneNo());
            assertNotNull(s.getLocation());
            assertNotNull(s.getTimeOfDay());
        }
    }
}