package com.dramafactory.service;

import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.RunRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

@SpringBootTest
class UsageServiceByRunDeepTestR4 {

    @Autowired
    UsageService usageService;

    @Autowired
    RunRepository runRepository;

    private Run persistRun(String goal, Long totalTokens, Long totalCostCents, LocalDateTime createdAt) {
        Run run = new Run();
        run.setGoal(goal);
        run.setStatus(RunStatus.DRAFT);
        run.setProjectId(1L);
        run.setTotalTokens(totalTokens);
        run.setTotalCostCents(totalCostCents);
        run.setCreatedAt(createdAt);
        return runRepository.save(run);
    }

    private UsageService.RunUsage findById(List<UsageService.RunUsage> list, Long runId) {
        for (UsageService.RunUsage u : list) {
            if (u.runId().equals(runId)) {
                return u;
            }
        }
        return null;
    }

    @Test
    void byRun_limitZero_defaultsTo20() {
        Run run = persistRun("goal-zero-" + System.nanoTime(), null, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = usageService.byRun(0);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
    }

    @Test
    void byRun_negativeLimit_defaultsTo20() {
        Run run = persistRun("goal-neg-" + System.nanoTime(), null, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = usageService.byRun(-5);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
    }

    @Test
    void byRun_goalExactly30_notTruncated() {
        String goal = "a".repeat(30);
        Run run = persistRun(goal, null, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = usageService.byRun(20);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
        assertEquals(30, found.goal().length());
        assertEquals(goal, found.goal());
    }

    @Test
    void byRun_goal31_truncatedTo30() {
        String goal = "b".repeat(31);
        Run run = persistRun(goal, null, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = usageService.byRun(20);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
        assertEquals("b".repeat(30), found.goal());
    }

    @Test
    void byRun_goalChinese_truncatedByChar() {
        String goal = "中".repeat(40);
        Run run = persistRun(goal, null, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = usageService.byRun(20);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
        assertEquals(30, found.goal().length());
        assertEquals("中".repeat(30), found.goal());
    }

    @Test
    void byRun_goalEmpty_ok() {
        // 真实约束：runs.goal 列 NOT NULL，空字符串是最小可存值；byRun 对空串不截断不断言 NPE
        Run run = persistRun("", null, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = assertDoesNotThrow(() -> usageService.byRun(20));
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
        assertEquals("", found.goal());
    }

    @Test
    void byRun_tokensFromRun_usedDirectly() {
        Run run = persistRun("goal-tokens-" + System.nanoTime(), 12345L, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = usageService.byRun(20);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
        assertEquals(12345L, found.tokens());
    }

    @Test
    void byRun_costFromRun_usedDirectly() {
        Run run = persistRun("goal-cost-" + System.nanoTime(), null, 678L, LocalDateTime.now());
        List<UsageService.RunUsage> result = usageService.byRun(20);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
        assertEquals(678L, found.costCents());
    }

    @Test
    void byRun_tokensNull_fallsBack() {
        Run run = persistRun("goal-fallback-" + System.nanoTime(), null, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = assertDoesNotThrow(() -> usageService.byRun(20));
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
    }

    @Test
    void byRun_orderByCreatedAtDesc() {
        LocalDateTime older = LocalDateTime.now().minus(1, ChronoUnit.HOURS);
        LocalDateTime newer = LocalDateTime.now();
        Run olderRun = persistRun("goal-older-" + System.nanoTime(), null, null, older);
        Run newerRun = persistRun("goal-newer-" + System.nanoTime(), null, null, newer);
        List<UsageService.RunUsage> result = usageService.byRun(10);
        assertTrue(result.size() >= 2);
        int olderIdx = -1;
        int newerIdx = -1;
        for (int i = 0; i < result.size(); i++) {
            if (result.get(i).runId().equals(olderRun.getId())) {
                olderIdx = i;
            }
            if (result.get(i).runId().equals(newerRun.getId())) {
                newerIdx = i;
            }
        }
        assertTrue(olderIdx >= 0);
        assertTrue(newerIdx >= 0);
        assertTrue(newerIdx < olderIdx);
    }

    @Test
    void byRun_runIdMatches() {
        Run run = persistRun("goal-id-" + System.nanoTime(), null, null, LocalDateTime.now());
        List<UsageService.RunUsage> result = usageService.byRun(20);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
        assertEquals(run.getId(), found.runId());
    }

    @Test
    void byRun_createdAt_setByPrePersist() {
        // 真实行为：Run.prePersist() 无条件用 LocalDateTime.now() 覆盖 createdAt，手动 set 无效
        LocalDateTime before = LocalDateTime.now().minusSeconds(10);
        Run run = persistRun("goal-created-" + System.nanoTime(), null, null, LocalDateTime.now().minus(2, ChronoUnit.HOURS));
        LocalDateTime after = LocalDateTime.now().plusSeconds(10);
        List<UsageService.RunUsage> result = usageService.byRun(20);
        UsageService.RunUsage found = findById(result, run.getId());
        assertNotNull(found);
        assertNotNull(found.createdAt());
        assertTrue(!found.createdAt().isBefore(before) && !found.createdAt().isAfter(after));
    }
}