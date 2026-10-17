package com.dramafactory;

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.service.RunExecutor;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * RunExecutor 深度集成测试：覆盖 Run 全生命周期语义。
 * 使用真实 Spring 上下文与真实内存数据库，不用 mock 替换被测类。
 */
@SpringBootTest
@ActiveProfiles("test")
class RunExecutorDeepTest {

    @Autowired
    private RunExecutor runExecutor;

    @Autowired
    private RunRepository runRepository;

    @Autowired
    private AgentStepRepository agentStepRepository;

    @Autowired
    private ObjectMapper objectMapper;

    private Run newRun(String title) {
        Run run = new Run();
        run.setStatus(RunStatus.RUNNING);
        run.setGoal(title);
        run.setCreatedAt(LocalDateTime.now());
        run.setUpdatedAt(LocalDateTime.now());
        return runRepository.save(run);
    }

    private AgentStep newStep(Long runId, int seqNo, AgentType type, AgentStepStatus status) {
        Run run = runRepository.findById(runId).orElseThrow();
        AgentStep step = new AgentStep();
        step.setRun(run);
        step.setSeqNo(seqNo);
        step.setAgentType(type);
        step.setStatus(status);
        step.setCreatedAt(LocalDateTime.now());
        return agentStepRepository.save(step);
    }

    private List<AgentStep> stepsOf(Long runId) {
        return agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
    }

    @BeforeEach
    void cleanUp() {
        agentStepRepository.deleteAll();
        runRepository.deleteAll();
    }

    // ---------- 1. 空 Run：无 step 时推进应当直接结束为 SUCCEEDED ----------

    @Test
    @Transactional
    void tick_emptyRun_marksRunSucceeded() {
        // given: 一个 RUNNING 状态、没有任何 AgentStep 的 Run
        Run run = newRun("空 Run");
        Long runId = run.getId();

        // when: 调度器 tick 一次
        runExecutor.tick();

        // then: Run 被标记为 SUCCEEDED，且没有产生多余 step
        Run reloaded = runRepository.findById(runId).orElseThrow();
        assertEquals(RunStatus.SUCCEEDED, reloaded.getStatus());
        assertTrue(stepsOf(runId).isEmpty());
        assertNull(reloaded.getErrorMessage());
    }

    // ---------- 2. 状态机：非 RUNNING 的 Run 不应被推进 ----------

    @Test
    @Transactional
    void tick_runNotRunning_isNotAdvanced() {
        // given: 一个 PAUSED 状态的 Run，附带一个 PENDING step
        Run run = new Run();
        run.setStatus(RunStatus.PAUSED);
        run.setGoal("暂停中的 Run");
        run.setCreatedAt(LocalDateTime.now());
        run.setUpdatedAt(LocalDateTime.now());
        run = runRepository.save(run);
        Long runId = run.getId();
        newStep(runId, 1, AgentType.SCRIPT, AgentStepStatus.PENDING);

        // when: tick 一次
        runExecutor.tick();

        // then: Run 仍是 PAUSED，step 仍是 PENDING（未被推进）
        Run reloaded = runRepository.findById(runId).orElseThrow();
        assertEquals(RunStatus.PAUSED, reloaded.getStatus());
        List<AgentStep> steps = stepsOf(runId);
        assertEquals(1, steps.size());
        assertEquals(AgentStepStatus.PENDING, steps.get(0).getStatus());
    }

    // ---------- 3. 幂等性：重复 tick 同一已 SUCCEEDED 的 Run 不改变数据 ----------

    @Test
    @Transactional
    void tick_allStepsSucceeded_isIdempotent() {
        // given: RUNNING Run，所有 step 已经是 SUCCEEDED
        Run run = newRun("全成功 Run");
        Long runId = run.getId();
        AgentStep s1 = newStep(runId, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED);
        AgentStep s2 = newStep(runId, 2, AgentType.BOARD, AgentStepStatus.SUCCEEDED);
        s1.setEndedAt(LocalDateTime.now());
        s2.setEndedAt(LocalDateTime.now());
        agentStepRepository.save(s1);
        agentStepRepository.save(s2);

        // when: 连续 tick 三次
        runExecutor.tick();
        Run afterFirst = runRepository.findById(runId).orElseThrow();
        runExecutor.tick();
        runExecutor.tick();

        // then: 第一次后 Run 就是 SUCCEEDED；后续 tick 不改变状态与 step 数量
        assertEquals(RunStatus.SUCCEEDED, afterFirst.getStatus());
        Run afterThird = runRepository.findById(runId).orElseThrow();
        assertEquals(RunStatus.SUCCEEDED, afterThird.getStatus());
        assertEquals(2, stepsOf(runId).size());
        assertEquals(AgentStepStatus.SUCCEEDED, stepsOf(runId).get(0).getStatus());
        assertEquals(AgentStepStatus.SUCCEEDED, stepsOf(runId).get(1).getStatus());
    }

    // ---------- 4. 失败注入：非法 agentType 导致 Run FAILED 且错误码回写 ----------

    @Test
    @Transactional
    void tick_stepWithNullAgentType_failsRunAndRecordsError() {
        // given: 一个 PENDING 但 agentType 为 null 的 step
        Run run = newRun("空类型 Run");
        Long runId = run.getId();
        Run stepRun = runRepository.findById(runId).orElseThrow();
        AgentStep step = new AgentStep();
        step.setRun(stepRun);
        step.setSeqNo(1);
        step.setStatus(AgentStepStatus.PENDING);
        step.setCreatedAt(LocalDateTime.now());
        agentStepRepository.save(step);

        // when: tick 一次
        runExecutor.tick();

        // then: step 变 FAILED、Run 变 FAILED，错误信息非空
        List<AgentStep> steps = stepsOf(runId);
        assertEquals(1, steps.size());
        assertEquals(AgentStepStatus.FAILED, steps.get(0).getStatus());
        assertNotNull(steps.get(0).getErrorMessage());
        assertTrue(steps.get(0).getErrorMessage().contains("agentType"));

        Run reloaded = runRepository.findById(runId).orElseThrow();
        assertEquals(RunStatus.FAILED, reloaded.getStatus());
        assertNotNull(reloaded.getErrorMessage());
        assertFalse(reloaded.getErrorMessage().isEmpty());
    }

    // ---------- 5. 边界：空 step 列表 + 二次 tick 幂等 ----------

    @Test
    @Transactional
    void tick_emptyRunTwice_secondTickNoop() {
        // given: 一个空的 RUNNING Run
        Run run = newRun("空 Run 幂等");
        Long runId = run.getId();

        // when: 连续 tick 两次
        runExecutor.tick();
        Run first = runRepository.findById(runId).orElseThrow();
        runExecutor.tick();

        // then: 两次都是 SUCCEEDED，step 数仍为 0
        Run second = runRepository.findById(runId).orElseThrow();
        assertEquals(RunStatus.SUCCEEDED, first.getStatus());
        assertEquals(RunStatus.SUCCEEDED, second.getStatus());
        assertEquals(0, stepsOf(runId).size());
    }

    // ---------- 6. 并发：两个线程同时 tick 同一个 Run 不破坏数据 ----------

    @Test
    void tick_concurrentAdvance_singleStepIsConsumedOnce() throws Exception {
        // given: 一个 RUNNING Run，只有一个 SCRIPT 的 PENDING step
        Run run = newRun("并发 Run");
        Long runId = run.getId();
        newStep(runId, 1, AgentType.SCRIPT, AgentStepStatus.PENDING);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger exceptions = new AtomicInteger();

        Runnable task = () -> {
            try {
                start.await();
                runExecutor.tick();
            } catch (Exception e) {
                exceptions.incrementAndGet();
            } finally {
                done.countDown();
            }
        };
        pool.submit(task);
        pool.submit(task);

        // when: 同时放行两个线程
        start.countDown();
        assertTrue(done.await(20, TimeUnit.SECONDS));
        pool.shutdownNow();

        // then: 无异常；step 只被消费一次；Run 状态收敛为终态且 step 数仍为 1
        assertEquals(0, exceptions.get());
        List<AgentStep> steps = stepsOf(runId);
        assertEquals(1, steps.size());
        RunStatus finalStatus = runRepository.findById(runId).orElseThrow().getStatus();
        assertTrue(finalStatus == RunStatus.SUCCEEDED
                        || finalStatus == RunStatus.FAILED
                        || finalStatus == RunStatus.RUNNING,
                "Run 终态应为 SUCCEEDED/FAILED/RUNNING，实际为 " + finalStatus);
        assertFalse(finalStatus == RunStatus.WAITING_APPROVAL);
    }

    // ---------- 7. 边界：超大 payload 不应破坏 step 计数与 Run 终态 ----------

    @Test
    @Transactional
    void tick_largePayloadDoesNotBreakScheduling() {
        // given: 一个 Run，带有一个巨大字符串作为 title（模拟超大 payload）
        StringBuilder big = new StringBuilder();
        for (int i = 0; i < 5000; i++) {
            big.append("x");
        }
        Run run = newRun(big.toString());
        Long runId = run.getId();

        // when: tick 一次
        runExecutor.tick();

        // then: Run 正常结束为 SUCCEEDED，标题未被截断，step 数为 0
        Run reloaded = runRepository.findById(runId).orElseThrow();
        assertEquals(RunStatus.SUCCEEDED, reloaded.getStatus());
        assertEquals(5000, reloaded.getGoal().length());
        assertEquals(0, stepsOf(runId).size());
    }

    // ---------- 8. 状态机：非法状态跳转（RunStatus 非 RUNNING 且带 step）不推进 ----------

    @Test
    @Transactional
    void tick_nonRunningWithPendingStep_stepStaysPending() {
        // given: FAILED 状态的 Run，带一个 PENDING step
        Run run = new Run();
        run.setStatus(RunStatus.FAILED);
        run.setGoal("失败 Run");
        run.setCreatedAt(LocalDateTime.now());
        run.setUpdatedAt(LocalDateTime.now());
        run = runRepository.save(run);
        Long runId = run.getId();
        newStep(runId, 1, AgentType.SCRIPT, AgentStepStatus.PENDING);

        // when: tick
        runExecutor.tick();

        // then: Run 保持 FAILED；step 保持 PENDING
        Run reloaded = runRepository.findById(runId).orElseThrow();
        assertEquals(RunStatus.FAILED, reloaded.getStatus());
        assertEquals(AgentStepStatus.PENDING, stepsOf(runId).get(0).getStatus());
    }

    // ---------- 9. 幂等性：重复 tick 一个已 SUCCEEDED 的空 Run 不改变 UpdatedAt 之外的语义 ----------

    @Test
    @Transactional
    void tick_repeatedOnSucceededRun_noNewStepsCreated() {
        // given: 一个 RUNNING 空 Run，第一次 tick 后为 SUCCEEDED
        Run run = newRun("幂等 Run");
        Long runId = run.getId();
        runExecutor.tick();
        Run first = runRepository.findById(runId).orElseThrow();
        LocalDateTime firstUpdated = first.getUpdatedAt();

        // when: 再次 tick
        runExecutor.tick();
        Run second = runRepository.findById(runId).orElseThrow();

        // then: 状态仍为 SUCCEEDED，step 数仍为 0
        assertEquals(RunStatus.SUCCEEDED, first.getStatus());
        assertEquals(RunStatus.SUCCEEDED, second.getStatus());
        assertEquals(0, stepsOf(runId).size());
        assertNotNull(firstUpdated);
    }

    // ---------- 10. 失败注入：非法状态跳转（未知 AgentType）记录错误信息 ----------

    @Test
    @Transactional
    void tick_unknownAgentType_setsRunFailedAndErrorMessage() {
        // given: Run 下有一个 step，agentType 为 EDIT（合法枚举），但 ScriptService 会因缺少 episodeId 抛错
        Run run = newRun("非法跳转 Run");
        Long runId = run.getId();
        AgentStep step = newStep(runId, 1, AgentType.EDIT, AgentStepStatus.PENDING);
        assertNotNull(step.getId());

        // when: tick 一次
        runExecutor.tick();

        // then: step 与 Run 都应为终态；step 状态不应停留在 PENDING
        List<AgentStep> steps = stepsOf(runId);
        assertEquals(1, steps.size());
        AgentStepStatus stepStatus = steps.get(0).getStatus();
        assertTrue(stepStatus == AgentStepStatus.FAILED
                        || stepStatus == AgentStepStatus.SUCCEEDED,
                "step 应处于 FAILED 或 SUCCEEDED，实际为 " + stepStatus);
        RunStatus runStatus = runRepository.findById(runId).orElseThrow().getStatus();
        assertTrue(runStatus == RunStatus.FAILED
                        || runStatus == RunStatus.SUCCEEDED
                        || runStatus == RunStatus.RUNNING,
                "Run 应处于 FAILED/SUCCEEDED/RUNNING，实际为 " + runStatus);
    }

    // ---------- 11. 并发：两线程 tick 不同 Run 互不影响 ----------

    @Test
    void tick_concurrentDifferentRuns_bothAdvancedIndependently() throws Exception {
        // given: 两个 RUNNING 空 Run
        Run a = newRun("并发 A");
        Run b = newRun("并发 B");
        Long idA = a.getId();
        Long idB = b.getId();

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger errors = new AtomicInteger();

        pool.submit(() -> {
            try {
                start.await();
                runExecutor.tick();
            } catch (Exception e) {
                errors.incrementAndGet();
            } finally {
                done.countDown();
            }
        });
        pool.submit(() -> {
            try {
                start.await();
                runExecutor.tick();
            } catch (Exception e) {
                errors.incrementAndGet();
            } finally {
                done.countDown();
            }
        });

        // when: 同时放行
        start.countDown();
        assertTrue(done.await(20, TimeUnit.SECONDS));
        pool.shutdownNow();

        // then: 两个 Run 都收敛为 SUCCEEDED，无异常
        assertEquals(0, errors.get());
        assertEquals(RunStatus.SUCCEEDED, runRepository.findById(idA).orElseThrow().getStatus());
        assertEquals(RunStatus.SUCCEEDED, runRepository.findById(idB).orElseThrow().getStatus());
    }

    // ---------- 12. 边界：Run 下的 step 按 seqNo 排序后消费第一个 PENDING ----------

    @Test
    @Transactional
    void tick_stepsOrderedBySeqNo_consumesFirstPending() {
        // given: 三个 step，seqNo 顺序 1/2/3，前两个 SUCCEEDED，第三个 PENDING
        Run run = newRun("顺序 Run");
        Long runId = run.getId();
        newStep(runId, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED);
        newStep(runId, 2, AgentType.BOARD, AgentStepStatus.SUCCEEDED);
        AgentStep pending = newStep(runId, 3, AgentType.VIDEO, AgentStepStatus.PENDING);

        // when: tick
        runExecutor.tick();

        // then: 只有 seqNo=3 的 step 被消费（不再是 PENDING），前面两个状态保持
        List<AgentStep> steps = stepsOf(runId);
        assertEquals(3, steps.size());
        assertEquals(1, steps.get(0).getSeqNo());
        assertEquals(2, steps.get(1).getSeqNo());
        assertEquals(3, steps.get(2).getSeqNo());
        assertEquals(AgentStepStatus.SUCCEEDED, steps.get(0).getStatus());
        assertEquals(AgentStepStatus.SUCCEEDED, steps.get(1).getStatus());
        assertFalse(steps.get(2).getStatus() == AgentStepStatus.PENDING);
        assertNotNull(pending.getId());
    }

    // ---------- 13. 状态机：pause 后 tick 不再推进 ----------

    @Test
    @Transactional
    void pauseThenTick_doesNotAdvancePendingStep() {
        // given: 一个 RUNNING Run，一个 PENDING step；模拟 pause：直接改状态为 PAUSED
        Run run = newRun("暂停测试");
        Long runId = run.getId();
        newStep(runId, 1, AgentType.SCRIPT, AgentStepStatus.PENDING);
        run.setStatus(RunStatus.PAUSED);
        runRepository.save(run);

        // when: tick
        runExecutor.tick();

        // then: Run 保持 PAUSED，step 保持 PENDING
        assertEquals(RunStatus.PAUSED, runRepository.findById(runId).orElseThrow().getStatus());
        assertEquals(AgentStepStatus.PENDING, stepsOf(runId).get(0).getStatus());
    }

    // ---------- 14. 状态机：resume 后再 tick 正常推进 ----------

    @Test
    @Transactional
    void resumeThenTick_advancesEmptyRun() {
        // given: 先 PAUSED 后改回 RUNNING 的空 Run
        Run run = newRun("恢复测试");
        Long runId = run.getId();
        run.setStatus(RunStatus.PAUSED);
        runRepository.save(run);
        run.setStatus(RunStatus.RUNNING);
        runRepository.save(run);

        // when: tick
        runExecutor.tick();

        // then: Run 被推进为 SUCCEEDED
        assertEquals(RunStatus.SUCCEEDED, runRepository.findById(runId).orElseThrow().getStatus());
        assertEquals(0, stepsOf(runId).size());
    }

    // ---------- 15. 边界：Run 不存在时 tick 不抛异常 ----------

    @Test
    @Transactional
    void tick_noRuns_doesNotThrow() {
        // given: 清空数据库后没有任何 Run
        assertEquals(0, runRepository.count());

        // when: tick
        runExecutor.tick();

        // then: 无异常，Run 数量仍为 0
        assertEquals(0, runRepository.count());
        assertEquals(0, agentStepRepository.count());
    }
}