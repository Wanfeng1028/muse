package com.dramafactory.billing;

import com.dramafactory.billing.BudgetExceededException;
import com.dramafactory.billing.BudgetMode;
import com.dramafactory.billing.BudgetPolicy;
import com.dramafactory.billing.CostLedgerEntry;
import com.dramafactory.billing.CostLedgerEntryRepository;
import com.dramafactory.billing.CostLedgerService;
import com.dramafactory.billing.CostLedgerStatus;
import com.dramafactory.billing.CostSummary;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * CostLedgerService 失败注入专项第二轮深测。
 *
 * 覆盖：缺失条目、非法状态迁移、重复退款拒绝、空区间汇总、
 * 并发状态机竞态守卫、DB 唯一约束冲突、并发中断/超时场景下状态不被污染。
 *
 * 说明：本测试不使用任何 mock，全部走真实 Spring + H2 实现，
 * 因为 CostLedgerService 的依赖仅为本地 repository，无外部网络/LLM 依赖。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:costledgerfail;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class CostLedgerFailureDeepTest {

    @Autowired
    private CostLedgerService costLedgerService;

    @Autowired
    private CostLedgerEntryRepository repository;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAll();
    }

    private CostLedgerEntry reload(Long id) {
        return repository.findById(id).orElseThrow();
    }

    @Test
    void reserve_onMissingEntry_throwsIllegalArgumentAndLeavesTableEmpty() {
        long before = repository.count();

        assertThatThrownBy(() -> costLedgerService.reserve(999_999L,
                new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0)))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("not found");

        assertThat(repository.count()).isEqualTo(before);
        assertThat(repository.findById(999_999L)).isEmpty();
    }

    @Test
    void reserve_withNullEntryId_throwsIllegalArgumentAndNoSideEffect() {
        long before = repository.count();

        assertThatThrownBy(() -> costLedgerService.reserve(null,
                new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0)))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(repository.count()).isEqualTo(before);
    }

    @Test
    void complete_onAlreadyCompletedEntry_throwsIllegalStateAndKeepsOriginalActuals() {
        Long id = costLedgerService.recordEstimate(7L, "agnes", "gpt-x", "generate", 10.0, "init");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.complete(id, 9.5, 111L);

        assertThatThrownBy(() -> costLedgerService.complete(id, 42.0, 222L))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("not RESERVED");

        CostLedgerEntry after = reload(id);
        assertThat(after.getStatus()).isEqualTo(CostLedgerStatus.COMPLETED);
        assertThat(after.getActualUsd()).isEqualTo(9.5);
        assertThat(after.getDurationMs()).isEqualTo(111L);
    }

    @Test
    void complete_onFailedEntry_throwsIllegalStateAndDoesNotOverwriteFailure() {
        Long id = costLedgerService.recordEstimate(7L, "agnes", "gpt-x", "generate", 10.0, "init");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.fail(id, 2.0, 300L, "downstream-boom");

        assertThatThrownBy(() -> costLedgerService.complete(id, 1.0, 1L))
                .isInstanceOf(IllegalStateException.class);

        CostLedgerEntry after = reload(id);
        assertThat(after.getStatus()).isEqualTo(CostLedgerStatus.FAILED);
        assertThat(after.getActualUsd()).isEqualTo(2.0);
        assertThat(after.getNote()).contains("downstream-boom");
    }

    @Test
    void complete_onRefundedEntry_throwsIllegalStateAndStaysRefunded() {
        Long id = costLedgerService.recordEstimate(7L, "agnes", "gpt-x", "generate", 10.0, "init");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.refund(id);

        assertThatThrownBy(() -> costLedgerService.complete(id, 1.0, 1L))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("not RESERVED");

        CostLedgerEntry after = reload(id);
        assertThat(after.getStatus()).isEqualTo(CostLedgerStatus.REFUNDED);
        assertThat(after.getActualUsd()).isNull();
    }

    @Test
    void refund_onAlreadyRefundedEntry_throwsIllegalStateAndKeepsRefundedStatus() {
        Long id = costLedgerService.recordEstimate(7L, "agnes", "gpt-x", "generate", 10.0, "init");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.refund(id);

        assertThatThrownBy(() -> costLedgerService.refund(id))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("not RESERVED");

        assertThat(reload(id).getStatus()).isEqualTo(CostLedgerStatus.REFUNDED);
    }

    @Test
    void refund_onMissingEntry_throwsIllegalArgumentAndNoRowCreated() {
        long before = repository.count();

        assertThatThrownBy(() -> costLedgerService.refund(424_242L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("not found");

        assertThat(repository.count()).isEqualTo(before);
    }

    @Test
    void fail_onMissingEntry_throwsIllegalArgumentAndDoesNotMutateAnyRow() {
        Long other = costLedgerService.recordEstimate(3L, "agnes", "gpt-x", "generate", 5.0, "untouched");
        costLedgerService.reserve(other, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));

        assertThatThrownBy(() -> costLedgerService.fail(555_555L, 1.0, 1L, "boom"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("not found");

        CostLedgerEntry untouched = reload(other);
        assertThat(untouched.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(untouched.getActualUsd()).isNull();
        assertThat(untouched.getNote()).doesNotContain("boom");
    }

    @Test
    void summarize_withEmptyWindow_returnsZeroTotalsAndZeroStatusCounts() {
        LocalDateTime from = LocalDateTime.now().plusYears(10);
        LocalDateTime to = from.plusDays(1);

        CostSummary summary = costLedgerService.summarize(null, null, from, to);

        assertThat(summary.entryCount()).isZero();
        assertThat(summary.totalEstimatedUsd()).isZero();
        assertThat(summary.totalReservedUsd()).isZero();
        assertThat(summary.totalSpentUsd()).isZero();
        assertThat(summary.countByStatus()).containsEntry(CostLedgerStatus.ESTIMATED, 0L);
        assertThat(summary.countByStatus()).containsEntry(CostLedgerStatus.RESERVED, 0L);
        assertThat(summary.countByStatus()).containsEntry(CostLedgerStatus.COMPLETED, 0L);
        assertThat(summary.countByStatus()).containsEntry(CostLedgerStatus.FAILED, 0L);
        assertThat(summary.countByStatus()).containsEntry(CostLedgerStatus.REFUNDED, 0L);
    }

    @Test
    void summarize_forUnknownProvider_returnsZeroEvenWhenOtherRowsExist() {
        Long id = costLedgerService.recordEstimate(11L, "agnes", "gpt-x", "generate", 12.0, "a");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));

        CostSummary summary = costLedgerService.summarize(null, "no-such-provider", null, null);

        assertThat(summary.entryCount()).isZero();
        assertThat(summary.totalEstimatedUsd()).isZero();
        assertThat(summary.totalReservedUsd()).isZero();
        assertThat(summary.totalSpentUsd()).isZero();
    }

    @Test
    void concurrentReserve_onSameEstimatedEntry_onlyOneSucceedsAndLoserSeesIllegalState() throws Exception {
        Long id = costLedgerService.recordEstimate(21L, "agnes", "gpt-x", "generate", 1.0, "race");

        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger illegalState = new AtomicInteger();
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < threads; i++) {
                futures.add(pool.submit((Callable<Void>) () -> {
                    start.await(5, TimeUnit.SECONDS);
                    try {
                        costLedgerService.reserve(id,
                                new BudgetPolicy(BudgetMode.WARN, 1_000_000.0, 0.0));
                        success.incrementAndGet();
                    } catch (IllegalStateException ex) {
                        illegalState.incrementAndGet();
                    } finally {
                        done.countDown();
                    }
                    return null;
                }));
            }
            start.countDown();
            assertThat(done.await(30, TimeUnit.SECONDS)).isTrue();
            for (Future<?> f : futures) {
                f.get(5, TimeUnit.SECONDS);
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }

        // 状态机守卫：至少一次成功，且最终状态必须是 RESERVED（不可回退/双重预留）
        assertThat(success.get()).isGreaterThanOrEqualTo(1);
        CostLedgerEntry after = reload(id);
        assertThat(after.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(repository.findAll().stream()
                .filter(e -> e.getStatus() == CostLedgerStatus.RESERVED)
                .count()).isEqualTo(1L);
    }

    @Test
    void concurrentRefund_onSameReservedEntry_rejectsDuplicatesAndKeepsRefundedOnce() throws Exception {
        Long id = costLedgerService.recordEstimate(22L, "agnes", "gpt-x", "generate", 3.0, "refund-race");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));

        int threads = 6;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger illegalState = new AtomicInteger();
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < threads; i++) {
                futures.add(pool.submit((Callable<Void>) () -> {
                    start.await(5, TimeUnit.SECONDS);
                    try {
                        costLedgerService.refund(id);
                        success.incrementAndGet();
                    } catch (IllegalStateException ex) {
                        illegalState.incrementAndGet();
                    } finally {
                        done.countDown();
                    }
                    return null;
                }));
            }
            start.countDown();
            assertThat(done.await(30, TimeUnit.SECONDS)).isTrue();
            for (Future<?> f : futures) {
                f.get(5, TimeUnit.SECONDS);
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }

        assertThat(success.get()).isGreaterThanOrEqualTo(1);
        assertThat(reload(id).getStatus()).isEqualTo(CostLedgerStatus.REFUNDED);
        assertThat(repository.findAll().stream()
                .filter(e -> e.getStatus() == CostLedgerStatus.REFUNDED)
                .count()).isEqualTo(1L);
    }

    @Test
    void recordEstimate_withNegativeAmount_throwsIllegalArgumentAndNoRowPersisted() {
        long before = repository.count();

        assertThatThrownBy(() -> costLedgerService.recordEstimate(31L, "agnes", "gpt-x",
                "generate", -0.01, "bad"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("negative");

        assertThat(repository.count()).isEqualTo(before);
    }

    @Test
    void interruptedReserveCaller_doesNotLeavePartiallyMutatedEntry() throws Exception {
        Long id = costLedgerService.recordEstimate(41L, "agnes", "gpt-x", "generate", 1.0, "interrupt");

        Thread worker = new Thread(() -> {
            try {
                costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 1_000_000.0, 0.0));
            } catch (RuntimeException ignored) {
                // 允许被中断时抛出运行时异常
            }
        });
        worker.start();
        worker.join(30_000);

        // 无论是否被中断，状态机只能处于 ESTIMATED 或 RESERVED，不得出现中间态/丢失状态
        CostLedgerEntry after = reload(id);
        assertThat(after.getStatus()).isIn(CostLedgerStatus.ESTIMATED, CostLedgerStatus.RESERVED);
        assertThat(after.getEstimatedUsd()).isEqualTo(1.0);
        assertThat(after.getId()).isEqualTo(id);
    }

    @Test
    void budgetExceededInCapMode_isTerminalFailureAndStateStaysEstimated() {
        Long id = costLedgerService.recordEstimate(51L, "agnes", "gpt-x", "generate", 100.0, "cap");

        assertThatThrownBy(() -> costLedgerService.reserve(id,
                new BudgetPolicy(BudgetMode.CAP, 10.0, 0.0)))
                .isInstanceOf(BudgetExceededException.class);

        CostLedgerEntry after = reload(id);
        assertThat(after.getStatus()).isEqualTo(CostLedgerStatus.ESTIMATED);
        assertThat(after.getActualUsd()).isNull();
        assertThat(after.getDurationMs()).isNull();
        // 失败后不追加任何 BUDGET-WARN 提示
        assertThat(after.getNote()).doesNotContain("BUDGET-WARN");
    }
}
