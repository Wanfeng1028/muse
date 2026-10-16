package com.dramafactory.api;

import com.dramafactory.dto.Records;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.ProjectStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.FfmpegService;
import com.dramafactory.service.FinalCutService;
import com.dramafactory.service.VideoTaskService;
import com.dramafactory.service.video.MockVideoProvider;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 视频生产管线端到端测试（全部真实 bean，仅视频商用产品自带的 MockVideoProvider）。
 *
 * <p>链路：创建项目→剧集→分镜 → submit 视频任务 → processDueTasks 轮询
 * → mock 落盘真实 mp4 片段 → buildFinalCut 拼接+字幕 → 断言成片真实存在且时长&gt;0。</p>
 */
@SpringBootTest
@Transactional
class VideoPipelineE2eTest {

    @Autowired
    private DramaProjectRepository dramaProjectRepository;
    @Autowired
    private EpisodeRepository episodeRepository;
    @Autowired
    private ShotRepository shotRepository;
    @Autowired
    private VideoTaskRepository videoTaskRepository;
    @Autowired
    private VideoTaskService videoTaskService;
    @Autowired
    private FinalCutService finalCutService;
    @Autowired
    private FfmpegService ffmpegService;
    @Autowired
    private MockVideoProvider mockVideoProvider;

    @BeforeEach
    void setUp() {
        // mock 商立刻就绪，不等待
        mockVideoProvider.setReadyAfterMs(0);
    }

    @Test
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    @DisplayName("端到端：分镜→视频任务→成片，最终 mp4 真实存在且时长>0")
    void fullPipeline_producesRealMp4WithPositiveDuration() throws Exception {
        // ---------- 1. 项目 ----------
        DramaProject project = new DramaProject();
        project.setTitle("E2E 视频流水线测试项目");
        project.setGenre("测试");
        project.setSynopsis("验证从分镜到成片的完整链路");
        project.setStatus(ProjectStatus.DRAFT);
        project.setOwnerId("e2e");
        project = dramaProjectRepository.save(project);
        assertNotNull(project.getId());

        // ---------- 2. 剧集 ----------
        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode.setTitle("第一集");
        episode.setOutline("测试大纲");
        episode.setStatus(EpisodeStatus.DRAFT);
        episode = episodeRepository.save(episode);
        assertNotNull(episode.getId());

        // ---------- 3. 两个分镜（带对白，走字幕链路） ----------
        Shot shot1 = new Shot();
        shot1.setEpisode(episode);
        shot1.setShotNo(1);
        shot1.setShotSize(ShotSize.ZHONG_JING);
        shot1.setCameraMove(CameraMove.GU_DING);
        shot1.setDescription("清晨的城市远景");
        shot1.setDurationSeconds(2);
        shot1.setDialogue("好久不见。");
        shot1.setVideoPrompt("city morning wide shot, static camera");
        shot1 = shotRepository.save(shot1);

        Shot shot2 = new Shot();
        shot2.setEpisode(episode);
        shot2.setShotNo(2);
        shot2.setShotSize(ShotSize.TE_XIE);
        shot2.setCameraMove(CameraMove.TUI);
        shot2.setDescription("主角特写，推镜");
        shot2.setDurationSeconds(2);
        shot2.setDialogue("你还是老样子。");
        shot2.setVideoPrompt("close-up portrait, push in");
        shot2 = shotRepository.save(shot2);

        // ---------- 4. 提交视频任务 ----------
        for (Shot s : List.of(shot1, shot2)) {
            Records.SubmitOutcome outcome = videoTaskService.submit(s.getId());
            assertNotNull(outcome.task(), "提交应返回任务");
            assertNotNull(outcome.task().id(), "任务应有 ID");
        }

        // ---------- 5. 轮询驱动状态机，直到全部 DONE ----------
        long deadline = System.nanoTime() + Duration.ofSeconds(120).toNanos();
        boolean allDone = false;
        while (System.nanoTime() < deadline) {
            videoTaskService.processDueTasks();
            List<VideoTask> tasks = videoTaskRepository.findAll();
            if (tasks.size() == 2 && tasks.stream()
                    .allMatch(t -> t.getStatus() == VideoTaskStatus.DONE)) {
                allDone = true;
                break;
            }
            Thread.sleep(500L);
        }
        assertTrue(allDone, "视频任务应在 120 秒内全部 DONE");

        // 每个任务的本地文件真实存在且非空
        for (VideoTask task : videoTaskRepository.findAll()) {
            String localPath = task.getLocalPath();
            assertNotNull(localPath, "DONE 任务应有 localPath");
            Path p = Paths.get(localPath);
            assertTrue(Files.exists(p) && Files.isRegularFile(p),
                    "任务产出文件应真实存在: " + localPath);
            assertTrue(Files.size(p) > 0, "任务产出文件应非空: " + localPath);
        }

        // ---------- 6. 成片 ----------
        Records.FinalCutResponse cut = finalCutService.buildFinalCut(episode.getId());
        assertNotNull(cut, "成片应返回响应");
        assertEquals("READY", cut.status().name(), "成片状态应为 READY");
        String finalPath = cut.filePath();
        assertNotNull(finalPath, "成片应有 filePath");

        // ---------- 7. 真实 mp4 断言 ----------
        Path finalFile = Paths.get(finalPath);
        assertTrue(Files.exists(finalFile), "成片文件应真实存在: " + finalPath);
        assertTrue(Files.isRegularFile(finalFile), "成片应为常规文件");
        assertTrue(Files.size(finalFile) > 0, "成片文件大小应大于 0");
        double duration = ffmpegService.probeDurationSeconds(finalFile);
        assertTrue(duration > 0.0, "成片时长应大于 0，实际: " + duration);
    }
}
