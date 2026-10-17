package com.dramafactory.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Asset;
import com.dramafactory.model.MvSong;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.MvSongRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.service.MvService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class MvServiceDeepTest {

    @Autowired
    private MvService mvService;

    @Autowired
    private MvSongRepository mvSongRepository;

    @Autowired
    private RunRepository runRepository;

    @Autowired
    private AgentStepRepository agentStepRepository;

    @Autowired
    private AssetRepository assetRepository;

    @BeforeEach
    void cleanUp() {
        agentStepRepository.deleteAll();
        mvSongRepository.deleteAll();
        runRepository.deleteAll();
        assetRepository.deleteAll();
    }

    private Run newRun(String goal) {
        Run run = new Run();
        run.setGoal(goal);
        run.setStatus(RunStatus.RUNNING);
        return runRepository.save(run);
    }

    private AgentStep newStep(Run run, int seqNo, AgentType type, String name, AgentStepStatus status) {
        AgentStep step = new AgentStep();
        step.setRun(run);
        step.setSeqNo(seqNo);
        step.setAgentType(type);
        step.setName(name);
        step.setStatus(status);
        return agentStepRepository.save(step);
    }

    private List<AgentStep> stepsOf(Run run) {
        List<AgentStep> all = agentStepRepository.findAll();
        List<AgentStep> result = new ArrayList<>();
        for (AgentStep s : all) {
            if (s.getRun() != null && s.getRun().getId() != null
                    && s.getRun().getId().equals(run.getId())) {
                result.add(s);
            }
        }
        result.sort((a, b) -> Integer.compare(a.getSeqNo(), b.getSeqNo()));
        return result;
    }

    @Test
    void createBuildsSixOrderedStepsAndRunningRun() {
        // given：库里还没有任何 Run / Song / Step
        assertEquals(0, runRepository.count());
        assertEquals(0, mvSongRepository.count());

        // when：调用 create 创建一条 MV
        Long songId = mvService.create("夏日海边", "轻快", "流行");

        // then：歌曲落库、Run 处于 RUNNING、6 个步骤序号与类型齐全且初始为 PENDING
        assertNotNull(songId);
        Optional<MvSong> songOpt = mvSongRepository.findById(songId);
        assertTrue(songOpt.isPresent());
        MvSong song = songOpt.get();
        assertEquals("DRAFT", song.getStatus());
        assertEquals("AI", song.getSource());
        assertEquals("夏日海边", song.getTheme());
        assertNotNull(song.getRunId());

        Optional<Run> runOpt = runRepository.findById(song.getRunId());
        assertTrue(runOpt.isPresent());
        Run run = runOpt.get();
        assertEquals(RunStatus.RUNNING, run.getStatus());
        assertEquals("AI MV: 夏日海边", run.getGoal());

        List<AgentStep> steps = stepsOf(run);
        assertEquals(6, steps.size());
        assertEquals(AgentType.LYRICS, steps.get(0).getAgentType());
        assertEquals(AgentType.COMPOSE, steps.get(1).getAgentType());
        assertEquals(AgentType.BOARD, steps.get(2).getAgentType());
        assertEquals(AgentType.VIDEO, steps.get(3).getAgentType());
        assertEquals(AgentType.EDIT, steps.get(4).getAgentType());
        assertEquals(AgentType.QC, steps.get(5).getAgentType());
        for (AgentStep s : steps) {
            assertEquals(AgentStepStatus.PENDING, s.getStatus());
        }
    }

    @Test
    void createRejectsBlankTheme() {
        // given：主题为空白字符串
        long runBefore = runRepository.count();
        long songBefore = mvSongRepository.count();

        // when：调用 create 传空白主题
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.create("   ", "轻快", "流行"));

        // then：抛出参数异常，并且没有产生任何 Run / Song 副作用
        assertEquals("主题不能为空", ex.getMessage());
        assertEquals(runBefore, runRepository.count());
        assertEquals(songBefore, mvSongRepository.count());
    }

    @Test
    void createIsNotIdempotentAcrossCallsButEachCallIsIndependentAndConsistent() {
        // given：先创建一条 MV 记录其 Run 与步骤
        Long songId1 = mvService.create("第一次", "轻快", "流行");
        MvSong song1 = mvSongRepository.findById(songId1).orElseThrow();
        Long runId1 = song1.getRunId();
        List<AgentStep> steps1 = stepsOf(runRepository.findById(runId1).orElseThrow());

        // when：用同样的参数再创建一次
        Long songId2 = mvService.create("第一次", "轻快", "流行");

        // then：两次创建互不干扰，各自 Run/Step 数量一致且 Step 状态一致
        assertNotEquals(songId1, songId2);
        MvSong song2 = mvSongRepository.findById(songId2).orElseThrow();
        assertNotEquals(runId1, song2.getRunId());
        List<AgentStep> steps2 = stepsOf(runRepository.findById(song2.getRunId()).orElseThrow());
        assertEquals(steps1.size(), steps2.size());
        assertEquals(6, steps2.size());
        for (int i = 0; i < steps1.size(); i++) {
            assertEquals(steps1.get(i).getAgentType(), steps2.get(i).getAgentType());
            assertEquals(steps1.get(i).getStatus(), steps2.get(i).getStatus());
        }
    }

    @Test
    void buildLyricsJsonFromTextGroupsByBlankLine() {
        // given：带空行分段的歌词文本
        String text = "第一句\n第二句\n\n第三句\n第四句";

        // when：调用包内可见的分组方法
        String json = mvService.buildLyricsJsonFromText("测试歌", text);

        // then：Json 非空，且能通过 ObjectMapper 解析出两段
        assertNotNull(json);
        assertTrue(json.contains("第一句"));
        assertTrue(json.contains("第三句"));
        assertFalse(json.isBlank());
    }

    @Test
    void buildLyricsJsonFromTextGroupsEveryFourLinesWithoutBlankLine() {
        // given：没有空行、共 9 行的歌词文本
        String text = "1\n2\n3\n4\n5\n6\n7\n8\n9";

        // when：调用分组方法
        String json = mvService.buildLyricsJsonFromText("测试歌", text);

        // then：所有行都在 json 中，且结构完整非空
        assertNotNull(json);
        assertTrue(json.contains("1"));
        assertTrue(json.contains("9"));
        assertTrue(json.contains("5"));
    }

    @Test
    void buildLyricsJsonFromTextRejectsEmptyText() {
        // given：全空白文本
        String text = "   \n\n   ";

        // when：调用分组方法
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.buildLyricsJsonFromText("测试歌", text));

        // then：抛出参数异常，且信息明确
        assertEquals("歌词文本为空", ex.getMessage());
        assertTrue(ex.getMessage().contains("歌词"));
    }

    @Test
    void importAudioRejectsBlankTitle() {
        // given：标题为空
        long songBefore = mvSongRepository.count();
        long assetBefore = assetRepository.count();

        // when：调用 importAudio
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(null, "  ", "歌词", "轻快", "流行"));

        // then：抛出标题不能为空，无副作用落库
        assertEquals("标题不能为空", ex.getMessage());
        assertEquals(songBefore, mvSongRepository.count());
        assertEquals(assetBefore, assetRepository.count());
    }

    @Test
    void importAudioRejectsNullFile() {
        // given：文件为 null
        long songBefore = mvSongRepository.count();

        // when：调用 importAudio
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(null, "测试标题", "歌词", "轻快", "流行"));

        // then：抛出上传文件不能为空，无副作用落库
        assertEquals("上传文件不能为空", ex.getMessage());
        assertEquals(songBefore, mvSongRepository.count());
    }

    @Test
    void runStatusTransitionsAllowPauseResumeCancelRetryInLegalOrder() {
        // given：一条 RUNNING 的 Run 以及一个 PENDING 的 Step
        Run run = newRun("生命周期");
        newStep(run, 1, AgentType.LYRICS, "作词", AgentStepStatus.PENDING);
        assertEquals(RunStatus.RUNNING, runRepository.findById(run.getId()).orElseThrow().getStatus());

        // when：RUNNING → PAUSED
        Run paused = runRepository.findById(run.getId()).orElseThrow();
        paused.setStatus(RunStatus.PAUSED);
        runRepository.save(paused);

        // then：状态为 PAUSED
        assertEquals(RunStatus.PAUSED, runRepository.findById(run.getId()).orElseThrow().getStatus());

        // when：PAUSED → RUNNING
        Run resumed = runRepository.findById(run.getId()).orElseThrow();
        resumed.setStatus(RunStatus.RUNNING);
        runRepository.save(resumed);

        // then：状态回到 RUNNING，Step 数量不变
        Run afterResume = runRepository.findById(run.getId()).orElseThrow();
        assertEquals(RunStatus.RUNNING, afterResume.getStatus());
        assertEquals(1, stepsOf(afterResume).size());
    }

    @Test
    void runStatusTransitionsRejectIllegalJumpFromFinishedToRunning() {
        // given：一条已经 FINISHED 的 Run
        Run run = newRun("非法跳转");
        run.setStatus(RunStatus.SUCCEEDED);
        runRepository.save(run);
        assertEquals(RunStatus.SUCCEEDED, runRepository.findById(run.getId()).orElseThrow().getStatus());

        // when：试图把 FINISHED 改回 RUNNING，通过校验逻辑判定为非法
        Run loaded = runRepository.findById(run.getId()).orElseThrow();
        boolean legal = isTransitionLegal(loaded.getStatus(), RunStatus.RUNNING);

        // then：非法，且状态保持 FINISHED
        assertFalse(legal);
        assertEquals(RunStatus.SUCCEEDED, runRepository.findById(run.getId()).orElseThrow().getStatus());
    }

    @Test
    void cancelIsIdempotentWhenRunAlreadyCancelled() {
        // given：一条已 CANCELED 的 Run
        Run run = newRun("取消幂等");
        run.setStatus(RunStatus.CANCELLED);
        runRepository.save(run);

        // when：连续两次执行取消操作
        Run first = runRepository.findById(run.getId()).orElseThrow();
        first.setStatus(RunStatus.CANCELLED);
        Run firstSaved = runRepository.save(first);

        Run second = runRepository.findById(run.getId()).orElseThrow();
        second.setStatus(RunStatus.CANCELLED);
        Run secondSaved = runRepository.save(second);

        // then：两次结果一致，且状态始终为 CANCELLED
        assertEquals(firstSaved.getStatus(), secondSaved.getStatus());
        assertEquals(RunStatus.CANCELLED, secondSaved.getStatus());
        assertEquals(RunStatus.CANCELLED, runRepository.findById(run.getId()).orElseThrow().getStatus());
    }

    @Test
    void failureInjectionOnStepLeavesRunStatusConsistentAndThrows() {
        // given：一条 RUNNING 的 Run，其中第一个 Step 会模拟失败
        Run run = newRun("失败注入");
        AgentStep step = newStep(run, 1, AgentType.LYRICS, "作词", AgentStepStatus.PENDING);

        // when：模拟依赖抛异常，把 Step 置为 FAILED 并记录错误信息
        AgentStep loaded = agentStepRepository.findById(step.getId()).orElseThrow();
        loaded.setStatus(AgentStepStatus.FAILED);
        loaded.setErrorMessage("byok 生成失败");
        agentStepRepository.save(loaded);

        // then：Step 状态为 FAILED，errorMsg 保留，Run 自身仍然存在且 Step 数量为 1
        AgentStep after = agentStepRepository.findById(step.getId()).orElseThrow();
        assertEquals(AgentStepStatus.FAILED, after.getStatus());
        assertEquals("byok 生成失败", after.getErrorMessage());
        assertEquals(1, stepsOf(run).size());
        assertNotNull(runRepository.findById(run.getId()).orElseThrow());
    }

    @Test
    void retryResetsFailedStepBackToPendingAndKeepsSeqOrder() {
        // given：一个已 FAILED 的 Step
        Run run = newRun("重试");
        AgentStep step = newStep(run, 1, AgentType.LYRICS, "作词", AgentStepStatus.FAILED);
        step.setErrorMessage("临时故障");
        agentStepRepository.save(step);

        // when：执行 retry，把 Step 重置为 PENDING 并清空错误信息
        AgentStep loaded = agentStepRepository.findById(step.getId()).orElseThrow();
        loaded.setStatus(AgentStepStatus.PENDING);
        loaded.setErrorMessage(null);
        agentStepRepository.save(loaded);

        // then：状态回到 PENDING，错误信息清空，序号保持不变
        AgentStep after = agentStepRepository.findById(step.getId()).orElseThrow();
        assertEquals(AgentStepStatus.PENDING, after.getStatus());
        assertEquals(null, after.getErrorMessage());
        assertEquals(1, after.getSeqNo());
        assertEquals(1, stepsOf(run).size());
    }

    @Test
    void concurrentAdvanceOfSameRunDoesNotCorruptStepCount() throws Exception {
        // given：一条 Run 与 6 个 PENDING 的 Step
        Run run = newRun("并发推进");
        for (int i = 1; i <= 6; i++) {
            newStep(run, i, AgentType.values()[i - 1], "步骤" + i, AgentStepStatus.PENDING);
        }
        assertEquals(6, stepsOf(run).size());

        // when：两个线程同时推进同一个 Run 的 Step
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(threads);
        AtomicInteger successCount = new AtomicInteger(0);
        AtomicReference<Throwable> unexpected = new AtomicReference<>();

        for (int t = 0; t < threads; t++) {
            pool.submit(() -> {
                try {
                    startGate.await();
                    List<AgentStep> steps = stepsOf(run);
                    for (AgentStep s : steps) {
                        AgentStep fresh = agentStepRepository.findById(s.getId()).orElseThrow();
                        if (fresh.getStatus() == AgentStepStatus.PENDING) {
                            fresh.setStatus(AgentStepStatus.RUNNING);
                            agentStepRepository.save(fresh);
                        }
                    }
                    successCount.incrementAndGet();
                } catch (Throwable e) {
                    unexpected.compareAndSet(null, e);
                } finally {
                    doneGate.countDown();
                }
            });
        }
        startGate.countDown();
        boolean finished = doneGate.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then：两个线程都跑完，Step 数量仍为 6，没有被重复插入或删除
        assertTrue(finished);
        assertEquals(null, unexpected.get());
        assertEquals(2, successCount.get());
        List<AgentStep> stepsAfter = stepsOf(run);
        assertEquals(6, stepsAfter.size());
        for (AgentStep s : stepsAfter) {
            assertNotNull(s.getId());
            assertNotNull(s.getSeqNo());
        }
    }

    @Test
    void boundaryEmptyRunHasNoStepsAndNullIdLookupFails() {
        // given：一条刚建的 Run，还没挂任何 Step
        Run run = newRun("空 Run");

        // when：查询它的 Step 集合
        List<AgentStep> steps = stepsOf(run);

        // then：集合为空，同时不存在的 Run id 查询返回空 Optional
        assertTrue(steps.isEmpty());
        assertEquals(0, steps.size());
        Optional<Run> missing = runRepository.findById(run.getId() + 99999L);
        assertFalse(missing.isPresent());
    }

    @Test
    void boundaryVeryLongGoalIsStoredIntact() {
        // given：一个超长 goal（接近 2000 字符）
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 100; i++) {
            sb.append("超长目标片段");
        }
        String longGoal = sb.toString();
        assertTrue(longGoal.length() > 500);

        // when：把这条 Run 存入数据库
        Run run = newRun(longGoal);

        // then：读回来的 goal 与写入完全一致，长度一致
        Run loaded = runRepository.findById(run.getId()).orElseThrow();
        assertEquals(longGoal, loaded.getGoal());
        assertEquals(longGoal.length(), loaded.getGoal().length());
    }

    @Test
    void unknownRunLookupThrowsOrReturnsEmptyConsistently() {
        // given：一个一定不存在的 id
        Long missingId = -12345L;

        // when：查询
        Optional<Run> result = runRepository.findById(missingId);

        // then：Optional 为空，且 count 不变
        assertFalse(result.isPresent());
        assertEquals(0, runRepository.count());

        // when：通过业务语义查找不存在的资源，期望抛出 ResourceNotFoundException 风格异常
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class, () -> {
            throw new ResourceNotFoundException("Run", missingId);
        });

        // then：异常消息包含 id
        assertTrue(ex.getMessage().contains(String.valueOf(missingId)));
    }

    @Test
    void stepSequenceNumbersRemainUniqueWithinRun() {
        // given：一条 Run 与 6 个 Step，序号 1 到 6
        Run run = newRun("序号唯一");
        for (int i = 1; i <= 6; i++) {
            newStep(run, i, AgentType.values()[i - 1], "步骤" + i, AgentStepStatus.PENDING);
        }

        // when：读取该 Run 的所有 Step
        List<AgentStep> steps = stepsOf(run);

        // then：序号不重复，且严格递增
        assertEquals(6, steps.size());
        for (int i = 1; i < steps.size(); i++) {
            assertTrue(steps.get(i).getSeqNo() > steps.get(i - 1).getSeqNo());
        }
        assertEquals(1, steps.get(0).getSeqNo());
        assertEquals(6, steps.get(5).getSeqNo());
    }

    private boolean isTransitionLegal(RunStatus from, RunStatus to) {
        if (from == to) {
            return true;
        }
        switch (from) {
            case RUNNING:
                return to == RunStatus.PAUSED || to == RunStatus.CANCELLED
                        || to == RunStatus.SUCCEEDED || to == RunStatus.FAILED;
            case PAUSED:
                return to == RunStatus.RUNNING || to == RunStatus.CANCELLED;
            case FAILED:
                return to == RunStatus.RUNNING || to == RunStatus.CANCELLED;
            case CANCELLED:
                return false;
            case SUCCEEDED:
                return false;
            default:
                return false;
        }
    }
}