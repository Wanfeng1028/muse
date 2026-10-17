package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.DramaProject;import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.DramaProjectRepository;import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.VideoTaskService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class VideoTaskServiceDeepTest {

    @Autowired
    private VideoTaskService videoTaskService;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository projectRepository;
    private Long shotId;

    @BeforeEach
    void setUp() {
        DramaProject project = new DramaProject();
        project.setTitle("deep-test-project");        project = projectRepository.save(project);

        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode = episodeRepository.save(episode);

        Shot shot = new Shot();
        shot.setEpisode(episode);
        shot.setShotNo(1);
        shot.setDurationSeconds(5);
        shot = shotRepository.save(shot);

        shotId = shot.getId();
    }

    private VideoTask newTask(Long shotId, VideoTaskStatus status, int attempts) {
        Shot shot = shotRepository.findById(shotId).orElseThrow();
        VideoTask task = new VideoTask();
        task.setShot(shot);
        task.setProvider("mock");
        task.setStatus(status);
        task.setAttempts(attempts);
        task.setNextRetryAt(LocalDateTime.now());
        return videoTaskRepository.save(task);
    }

    @Test
    @Transactional
    void submit_createsPendingTask_whenNoActiveTaskExists() {
        long before = videoTaskRepository.count();

        Records.SubmitOutcome outcome = videoTaskService.submit(shotId);

        assertAll(
                () -> assertTrue(outcome.created(), "首次提交应新建任务"),
                () -> assertNotNull(outcome.task(), "返回的任务不能为空"),
                () -> assertEquals(VideoTaskStatus.PENDING, outcome.task().status(), "新建任务状态应为 PENDING"),
                () -> assertEquals(0, outcome.task().attempts(), "新建任务 attempts 应为 0"),
                () -> assertEquals(before + 1, videoTaskRepository.count(), "库里应新增一条任务")
        );
    }

    @Test
    @Transactional
    void submit_isIdempotent_forPendingTask() {
        Records.SubmitOutcome first = videoTaskService.submit(shotId);
        long countAfterFirst = videoTaskRepository.count();

        Records.SubmitOutcome second = videoTaskService.submit(shotId);

        assertAll(
                () -> assertFalse(second.created(), "重复提交不应新建任务"),
                () -> assertEquals(first.task().id(), second.task().id(), "两次提交应返回同一任务 id"),
                () -> assertEquals(countAfterFirst, videoTaskRepository.count(), "重复提交后任务总数不变")
        );
    }

    @Test
    @Transactional
    void submit_isIdempotent_forProcessingTask() {
        VideoTask processing = newTask(shotId, VideoTaskStatus.PROCESSING, 1);
        long countBefore = videoTaskRepository.count();

        Records.SubmitOutcome outcome = videoTaskService.submit(shotId);

        assertAll(
                () -> assertFalse(outcome.created(), "存在 PROCESSING 任务时不应新建"),
                () -> assertEquals(processing.getId(), outcome.task().id(), "应返回已有 PROCESSING 任务"),
                () -> assertEquals(VideoTaskStatus.PROCESSING, outcome.task().status(), "返回状态应为 PROCESSING"),
                () -> assertEquals(countBefore, videoTaskRepository.count(), "任务总数不变")
        );
    }

    @Test
    @Transactional
    void submit_createsNewTask_whenOnlyFailedTaskExists() {
        newTask(shotId, VideoTaskStatus.FAILED, 3);

        Records.SubmitOutcome outcome = videoTaskService.submit(shotId);

        assertAll(
                () -> assertTrue(outcome.created(), "仅有 FAILED 任务时应允许新建"),
                () -> assertEquals(VideoTaskStatus.PENDING, outcome.task().status(), "新任务应为 PENDING"),
                () -> assertEquals(2, videoTaskRepository.findByShotIdOrderByIdDesc(shotId).size(),
                        "库里应有 FAILED 与 PENDING 两条任务")
        );
    }

    @Test
    @Transactional
    void submit_throws_whenShotMissing() {
        Long missingShotId = 999_999_999L;

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> videoTaskService.submit(missingShotId),
                "镜头不存在时应抛 ResourceNotFoundException");
        assertAll(
                () -> assertNotNull(ex.getMessage(), "异常消息不能为空"),
                () -> assertTrue(ex.getMessage().contains("Shot") || ex.getMessage().contains("999999999"),
                        "异常消息应指明 Shot 或 id")
        );
    }

    @Test
    @Transactional
    void retry_resetsFailedTaskToPending() {
        VideoTask failed = newTask(shotId, VideoTaskStatus.FAILED, 4);
        failed.setErrorMessage("provider 崩了");
        videoTaskRepository.save(failed);

        Records.VideoTaskResponse response = videoTaskService.retry(failed.getId());

        assertAll(
                () -> assertEquals(VideoTaskStatus.PENDING, response.status(), "重试后状态应为 PENDING"),
                () -> assertEquals(0, response.attempts(), "重试后 attempts 应归零"),
                () -> assertNotNull(response.id(), "返回任务应有 id"),
                () -> {
                    VideoTask reloaded = videoTaskRepository.findById(failed.getId()).orElseThrow();
                    assertEquals(VideoTaskStatus.PENDING, reloaded.getStatus(), "库中状态应为 PENDING");
                    assertEquals(0, reloaded.getAttempts(), "库中 attempts 应为 0");
                    assertNull(reloaded.getErrorMessage(), "库中错误信息应被清空");
                }
        );
    }

    @Test
    @Transactional
    void retry_isIdempotent_whenCalledTwice() {
        VideoTask failed = newTask(shotId, VideoTaskStatus.FAILED, 2);
        failed.setErrorMessage("boom");
        videoTaskRepository.save(failed);

        Records.VideoTaskResponse first = videoTaskService.retry(failed.getId());

        assertAll(
                () -> assertEquals(VideoTaskStatus.PENDING, first.status(), "首次重试应得到 PENDING"),
                () -> assertThrows(IllegalStateException.class,
                        () -> videoTaskService.retry(failed.getId()),
                        "已回到 PENDING 的任务再次重试应抛 IllegalStateException"),
                () -> {
                    VideoTask reloaded = videoTaskRepository.findById(failed.getId()).orElseThrow();
                    assertEquals(VideoTaskStatus.PENDING, reloaded.getStatus(), "重复调用后库中状态仍为 PENDING");
                }
        );
    }

    @Test
    @Transactional
    void retry_throws_whenTaskNotFailed() {
        VideoTask pending = newTask(shotId, VideoTaskStatus.PENDING, 0);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> videoTaskService.retry(pending.getId()),
                "PENDING 任务重试应抛 IllegalStateException");
        assertAll(
                () -> assertTrue(ex.getMessage().contains("FAILED"), "异常消息应提到 FAILED"),
                () -> {
                    VideoTask reloaded = videoTaskRepository.findById(pending.getId()).orElseThrow();
                    assertEquals(VideoTaskStatus.PENDING, reloaded.getStatus(), "状态不应被改动");
                    assertEquals(0, reloaded.getAttempts(), "attempts 不应被改动");
                }
        );
    }

    @Test
    @Transactional
    void retry_throws_whenTaskMissing() {
        Long missingId = 888_888_888L;

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> videoTaskService.retry(missingId),
                "任务不存在时应抛 ResourceNotFoundException");
        assertAll(
                () -> assertNotNull(ex.getMessage(), "异常消息不能为空"),
                () -> assertTrue(ex.getMessage().contains("VideoTask") || ex.getMessage().contains("888888888"),
                        "异常消息应指明 VideoTask 或 id")
        );
    }

    @Test
    @Transactional
    void get_throws_whenTaskMissing() {
        Long missingId = 777_777_777L;

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> videoTaskService.get(missingId),
                "查询不存在的任务应抛 ResourceNotFoundException");
        assertAll(
                () -> assertNotNull(ex.getMessage(), "异常消息不能为空"),
                () -> assertTrue(ex.getMessage().contains("VideoTask") || ex.getMessage().contains("777777777"),
                        "异常消息应指明 VideoTask 或 id")
        );
    }

    @Test
    @Transactional
    void get_returnsTaskDetail() {
        Records.SubmitOutcome submitted = videoTaskService.submit(shotId);
        Long taskId = submitted.task().id();

        Records.VideoTaskResponse response = videoTaskService.get(taskId);

        assertAll(
                () -> assertEquals(taskId, response.id(), "返回 id 应与查询 id 一致"),
                () -> assertEquals(VideoTaskStatus.PENDING, response.status(), "状态应为 PENDING"),
                () -> assertEquals("mock", response.provider(), "provider 应为 mock")
        );
    }

    @Test
    @Transactional
    void listByShot_returnsTasksInDescendingIdOrder() {
        Records.SubmitOutcome first = videoTaskService.submit(shotId);
        videoTaskRepository.findById(first.task().id()).orElseThrow();
        VideoTask second = newTask(shotId, VideoTaskStatus.DONE, 1);

        List<Records.VideoTaskResponse> list = videoTaskService.listByShot(shotId);

        assertAll(
                () -> assertTrue(list.size() >= 2, "应至少返回两条任务"),
                () -> assertEquals(second.getId(), list.get(0).id(), "第一条应是 id 最大的任务"),
                () -> assertTrue(list.get(0).id() > list.get(1).id(), "结果应按 id 降序")
        );
    }

    @Test
    @Transactional
    void listByShot_returnsEmpty_whenNoTask() {
        DramaProject project = new DramaProject();
        project.setTitle("empty-project");        project = projectRepository.save(project);
        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode = episodeRepository.save(episode);
        Shot lonely = new Shot();
        lonely.setEpisode(episode);
        lonely.setShotNo(1);
        lonely.setDurationSeconds(5);
        lonely = shotRepository.save(lonely);

        List<Records.VideoTaskResponse> list = videoTaskService.listByShot(lonely.getId());

        assertAll(
                () -> assertNotNull(list, "返回值不能为 null"),
                () -> assertTrue(list.isEmpty(), "没有任务时应返回空列表")
        );
    }

    @Test
    @Transactional
    void submitAllForEpisode_createsOneTaskPerShot() {
        DramaProject project = new DramaProject();
        project.setTitle("multi-shot-project");        project = projectRepository.save(project);
        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(2);
        episode = episodeRepository.save(episode);

        for (int i = 1; i <= 3; i++) {
            Shot shot = new Shot();
            shot.setEpisode(episode);
            shot.setShotNo(i);
            shot.setDurationSeconds(5);
            shotRepository.save(shot);
        }

        List<Records.VideoTaskResponse> result = videoTaskService.submitAllForEpisode(episode.getId());

        Long firstShotId = shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).get(0).getId();
        assertAll(
                () -> assertEquals(3, result.size(), "三个镜头应返回三条任务"),
                () -> assertTrue(result.stream().allMatch(r -> r.status() == VideoTaskStatus.PENDING),
                        "所有任务状态应为 PENDING"),
                () -> assertEquals(1, videoTaskRepository.findByShotIdOrderByIdDesc(firstShotId).size(),
                        "第一个镜头应恰好有一条任务")
        );
    }

    @Test
    @Transactional
    void submitAllForEpisode_isIdempotent_onSecondCall() {
        DramaProject project = new DramaProject();
        project.setTitle("idempotent-batch-project");        project = projectRepository.save(project);
        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(3);
        episode = episodeRepository.save(episode);

        for (int i = 1; i <= 2; i++) {
            Shot shot = new Shot();
            shot.setEpisode(episode);
            shot.setShotNo(i);
            shot.setDurationSeconds(5);
            shotRepository.save(shot);
        }

        List<Records.VideoTaskResponse> firstCall = videoTaskService.submitAllForEpisode(episode.getId());
        long countAfterFirst = videoTaskRepository.count();

        List<Records.VideoTaskResponse> secondCall = videoTaskService.submitAllForEpisode(episode.getId());

        assertAll(
                () -> assertEquals(2, firstCall.size(), "首次批量提交应返回两条任务"),
                () -> assertEquals(2, secondCall.size(), "再次批量提交应返回两条任务"),
                () -> assertEquals(countAfterFirst, videoTaskRepository.count(), "二次提交不应新建任务"),
                () -> assertTrue(firstCall.stream().map(Records.VideoTaskResponse::id).sorted().toList()
                                .equals(secondCall.stream().map(Records.VideoTaskResponse::id).sorted().toList()),
                        "两次调用应返回相同的任务 id 集合")
        );
    }
}