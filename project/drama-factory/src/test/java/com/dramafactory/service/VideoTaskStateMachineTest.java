package com.dramafactory.service;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.dto.Records;
import com.dramafactory.model.ShotSize;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.MockVideoProvider;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

/**
 * VideoTaskService 状态机集成测试。
 *
 * 使用 @SpringBootTest 加载测试环境配置（test/resources/application.yml，H2 内存库），
 * 通过真实 Repository 落库，并用 MockVideoProvider 模拟视频生成过程，
 * 覆盖：提交创建 PENDING 任务、完整流转到 DONE、失败重试路径、退避时间指数增长等场景。
 */
@SpringBootTest
@TestPropertySource(properties = "drama.video.poll-interval-ms=3600000")
class VideoTaskStateMachineTest {

    @Autowired
    private VideoTaskService videoTaskService;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository dramaProjectRepository;

    @Autowired
    private MockVideoProvider mockVideoProvider;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    /**
     * 辅助方法：构建一条完整的 项目 -> 剧集 -> 分镜 数据链并落库，返回分镜 ID。
     */
    private Long createShot() {
        // 1. 创建项目
        DramaProject project = new DramaProject();
        project.setTitle("测试项目");
        project = dramaProjectRepository.save(project);

        // 2. 创建剧集
        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode.setTitle("第一集");
        episode = episodeRepository.save(episode);

        // 3. 创建分镜
        Shot shot = new Shot();
        shot.setEpisode(episode);
        shot.setShotNo(1);
        shot.setShotSize(ShotSize.ZHONG_JING);
        shot.setCameraMove(CameraMove.GU_DING);
        shot.setDescription("测试画面");
        shot.setDurationSeconds(2);
        shot.setDialogue("测试对白");
        shot.setVideoPrompt("test prompt");
        shot = shotRepository.save(shot);

        return shot.getId();
    }

    /**
     * 测试辅助：将任务的下次重试时间拨到过去，使其可被 processDueTasks() 立即处理。
     * （生产环境 nextRetryAt 由轮询间隔/退避决定；测试用此手段确定性地推进状态机。）
     */
    private void resetDue(Long taskId) {
        videoTaskRepository.findById(taskId).ifPresent(t -> {
            t.setNextRetryAt(java.time.LocalDateTime.now().minusSeconds(5));
            videoTaskRepository.save(t);
        });
    }

    /**
     * 测试 1：submit(shotId) 应创建一个状态为 PENDING 的视频任务。
     */
    @Test
    @DisplayName("提交分镜后创建 PENDING 状态的任务")
    void submitCreatesPendingTask() {
        Long shotId = createShot();

        Records.VideoTaskResponse task = videoTaskService.submit(shotId).task();

        Assertions.assertNotNull(task, "提交后应返回任务对象");
        Assertions.assertNotNull(task.id(), "任务应已持久化并拥有主键");
        Assertions.assertEquals(VideoTaskStatus.PENDING, task.status(),
                "新提交的任务状态应为 PENDING");
    }

    /**
     * 测试 2：完整流转到 DONE。
     *
     * MockVideoProvider 设置 readyAfterMs(0) 表示立即可用；
     * 第一次 processDueTasks() 将 PENDING 推进到 PROCESSING（开始生成），
     * 第二次 processDueTasks() 轮询到结果就绪，状态流转到 DONE 并生成本地文件。
     */
    @Test
    @DisplayName("完整流转：PENDING -> PROCESSING -> DONE，且生成本地文件")
    void fullCycleToDone() throws InterruptedException {
        Long shotId = createShot();
        mockVideoProvider.setReadyAfterMs(0);

        Records.VideoTaskResponse submitted = videoTaskService.submit(shotId).task();
        Long taskId = submitted.id();

        // 第一次调度：PENDING -> PROCESSING，触发 mock 生成
        videoTaskService.processDueTasks();
        // mock 已就绪（readyAfterMs=0），把 nextRetryAt 拨到过去让第二次调度立即轮询
        resetDue(taskId);

        // 第二次调度：轮询 -> COMPLETED -> 生成本地文件 -> DONE
        videoTaskService.processDueTasks();

        Records.VideoTaskResponse result = videoTaskService.get(taskId);
        Assertions.assertNotNull(result, "任务应可查询到");
        Assertions.assertEquals(VideoTaskStatus.DONE, result.status(),
                "经过完整调度后任务状态应为 DONE");
        Assertions.assertTrue(result.hasLocalFile(),
                "DONE 状态下应生成本地视频文件");
    }

    /**
     * 测试 3：失败路径。
     *
     * 设置 setFailNext(true) 让 mock 在生成阶段返回失败。
     * 第一次 processDueTasks() 将任务推进到 PROCESSING；
     * 第二次 processDueTasks() 轮询到失败结果，触发重试退避逻辑，attempts 增加。
     * 为避免依赖 maxAttempts 的具体数值造成测试缓慢，这里只断言 attempts >= 1。
     */
    @Test
    @DisplayName("失败路径：两次调度后任务进入重试，attempts 递增")
    void failPath() throws InterruptedException {
        Long shotId = createShot();
        mockVideoProvider.setReadyAfterMs(0);
        mockVideoProvider.setFailNext(true);

        Records.VideoTaskResponse submitted = videoTaskService.submit(shotId).task();
        Long taskId = submitted.id();

        // 第一次调度：PENDING -> PROCESSING
        videoTaskService.processDueTasks();
        resetDue(taskId);

        // 第二次调度：轮询到失败结果（failNext），触发重试退避逻辑，attempts 增加
        videoTaskService.processDueTasks();

        Records.VideoTaskResponse result = videoTaskService.get(taskId);
        Assertions.assertNotNull(result, "任务应可查询到");
        Assertions.assertTrue(result.attempts() >= 1,
                "失败后重试计数 attempts 应至少为 1，实际为 " + result.attempts());
        Assertions.assertTrue(
                result.status() == VideoTaskStatus.PROCESSING
                        || result.status() == VideoTaskStatus.FAILED,
                "失败重试后状态应为 PROCESSING（等待重试）或 FAILED，实际为 " + result.status());
    }

    /**
     * 测试 4：退避时间指数增长并封顶。
     *
     * computeBackoffMs 为包可见静态方法，测试类同包可直接访问。
     * 期望：attempt 0 -> 10s，1 -> 20s，2 -> 40s，极大值封顶 600s。
     */
    @Test
    @DisplayName("退避时间指数增长并在 600000ms 封顶")
    void backoffIsExponential() {
        Assertions.assertEquals(10_000L, VideoTaskService.computeBackoffMs(0),
                "第 0 次退避应为 10 秒");
        Assertions.assertEquals(20_000L, VideoTaskService.computeBackoffMs(1),
                "第 1 次退避应为 20 秒");
        Assertions.assertEquals(40_000L, VideoTaskService.computeBackoffMs(2),
                "第 2 次退避应为 40 秒");
        Assertions.assertEquals(600_000L, VideoTaskService.computeBackoffMs(100),
                "退避时间应封顶为 600 秒（600000ms）");
    }
}
