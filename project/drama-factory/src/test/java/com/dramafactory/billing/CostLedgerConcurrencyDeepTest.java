package com.dramafactory.billing;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * CostLedgerService 的并发与状态机守卫深度测试。
 *
 * 注意：本实现里 CostLedgerEntry 没有幂等键字段，CostLedgerService 也没有任何
 * 接受幂等键的方法，仓储里也没有按幂等键查询的方法。所以"幂等"在这个实现里
 * 只有一条真实含义：状态机守卫——对同一条目重复做状态迁移会抛 IllegalStateException。
 * 去重是上游调用方的事，不是账本的事。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:costledgerconcdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class CostLedgerConcurrencyDeepTest {

    @Autowired
    private CostLedgerService costLedgerService;

    @Autowired
    private CostLedgerEntryRepository repository;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAll();
    }

    /**
     * 20 个线程同时建条目，看是不是一条不丢。
     * 期望：20 个 id 都不空、两两不同；库里 20 条；估算合计 20 * 2.5 = 50.0；ESTIMATED 计数 20。
     */
    @Test
    void concurrentRecordEstimateDoesNotLoseEntries() throws InterruptedException {
        int threads = 20;
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        List<Long> ids = new CopyOnWriteArrayList<>();
        List<Throwable> failures = new CopyOnWriteArrayList<>();

        for (int i = 0; i < threads; i++) {
            final int idx = i;
            Thread t = new Thread(() -> {
                try {
                    start.await();
                    Long id = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 2.5, "t-" + idx);
                    ids.add(id);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    failures.add(e);
                } catch (Throwable e) {
                    failures.add(e);
                } finally {
                    done.countDown();
                }
            });
            t.start();
        }

        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        assertThat(finished).as("所有线程应在 30 秒内跑完").isTrue();
        assertThat(failures).as("并发建条目不应抛异常").isEmpty();

        assertThat(ids).hasSize(threads);
        assertThat(ids).allSatisfy(id -> assertThat(id).isNotNull());
        assertThat(ids.stream().distinct().count()).as("20 个 id 应两两不同").isEqualTo(threads);

        assertThat(repository.count()).isEqualTo(20L);

        CostSummary summary = costLedgerService.summarize(1L, null, null, null);
        assertThat(summary.totalEstimatedUsd()).as("20 * 2.5 = 50.0").isEqualTo(50.0);
        assertThat(summary.countByStatus().get(CostLedgerStatus.ESTIMATED)).isEqualTo(20L);
    }

    /**
     * 10 个线程各自跑完整链路：建条目 -> 预留 -> 完成。
     * 期望：COMPLETED 10 条；实际花费合计 10 * 3.0 = 30.0；估算合计 10 * 4.0 = 40.0。
     */
    @Test
    void concurrentFullLifecycleKeepsAmountsCorrect() throws InterruptedException {
        int threads = 10;
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        List<Throwable> failures = new CopyOnWriteArrayList<>();

        for (int i = 0; i < threads; i++) {
            Thread t = new Thread(() -> {
                try {
                    start.await();
                    Long id = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 4.0, "c");
                    costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 10000.0, 0.0));
                    costLedgerService.complete(id, 3.0, 100L);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    failures.add(e);
                } catch (Throwable e) {
                    failures.add(e);
                } finally {
                    done.countDown();
                }
            });
            t.start();
        }

        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        assertThat(finished).as("所有线程应在 30 秒内跑完").isTrue();
        assertThat(failures).as("全链路并发不应抛异常").isEmpty();

        CostSummary summary = costLedgerService.summarize(1L, null, null, null);
        assertThat(summary.totalSpentUsd()).as("10 * 3.0 = 30.0").isEqualTo(30.0);
        assertThat(summary.countByStatus().get(CostLedgerStatus.COMPLETED)).isEqualTo(10L);
        assertThat(summary.totalEstimatedUsd()).as("10 * 4.0 = 40.0").isEqualTo(40.0);
    }

    /**
     * 重复做状态迁移会被守卫拦下，这就是本实现唯一的"幂等"含义。
     * 每一步重复都期望抛 IllegalStateException。
     */
    @Test
    void repeatedStateTransitionsAreRejected() {
        // 同一 id 调两次 reserve，第二次应抛
        Long id1 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 1.0, "n");
        costLedgerService.reserve(id1, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        assertThatThrownBy(() -> costLedgerService.reserve(id1, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0)))
                .isInstanceOf(IllegalStateException.class);

        // reserve 后调两次 complete，第二次应抛
        Long id2 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 1.0, "n");
        costLedgerService.reserve(id2, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.complete(id2, 1.0, 10L);
        assertThatThrownBy(() -> costLedgerService.complete(id2, 1.0, 10L))
                .isInstanceOf(IllegalStateException.class);

        // reserve 后调两次 refund，第二次应抛
        Long id3 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 1.0, "n");
        costLedgerService.reserve(id3, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.refund(id3);
        assertThatThrownBy(() -> costLedgerService.refund(id3))
                .isInstanceOf(IllegalStateException.class);

        // reserve 后调两次 fail，第二次应抛
        Long id4 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 1.0, "n");
        costLedgerService.reserve(id4, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.fail(id4, 1.0, 10L, "x");
        assertThatThrownBy(() -> costLedgerService.fail(id4, 1.0, 10L, "x"))
                .isInstanceOf(IllegalStateException.class);

        // complete 之后再调 fail 应抛（此时不是 RESERVED）
        Long id5 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 1.0, "n");
        costLedgerService.reserve(id5, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.complete(id5, 1.0, 10L);
        assertThatThrownBy(() -> costLedgerService.fail(id5, 1.0, 10L, "x"))
                .isInstanceOf(IllegalStateException.class);

        // fail 之后再调 refund 应抛（此时不是 RESERVED）
        Long id6 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 1.0, "n");
        costLedgerService.reserve(id6, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.fail(id6, 1.0, 10L, "x");
        assertThatThrownBy(() -> costLedgerService.refund(id6))
                .isInstanceOf(IllegalStateException.class);
    }

    /**
     * 相同参数调两次 recordEstimate 得到两个不同 id。
     * 这里没有幂等键，去重靠的是上游调用方，不是账本；账本只负责把两次都记下来。
     */
    @Test
    void identicalParamsProduceTwoDistinctEntries() {
        Long id1 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 2.0, "same");
        Long id2 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 2.0, "same");

        assertThat(id1).isNotNull();
        assertThat(id2).isNotNull();
        assertThat(id1).as("没有去重逻辑，两个 id 应该不同").isNotEqualTo(id2);

        CostSummary summary = costLedgerService.summarize(1L, null, null, null);
        assertThat(summary.entryCount()).isEqualTo(2L);
        assertThat(summary.totalEstimatedUsd()).as("2.0 + 2.0 = 4.0").isEqualTo(4.0);
    }

    /**
     * 异常中断后重放：预留完直接"崩"，条目还在库里还是 RESERVED；之后可以继续完成。
     * 另一条：失败之后"重试"走新记录，FAILED 和 COMPLETED 的 actual 都计入 spent。
     */
    @Test
    void interruptedFlowKeepsReservedStateAndRetryCreatesNewEntry() {
        // 中断模拟：reserve 完直接 return，不调 complete
        Long id = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 5.0, "n");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0));
        CostLedgerEntry reloaded = repository.findById(id).orElseThrow();
        assertThat(reloaded.getStatus()).as("中途崩了账还在库里，状态还是 RESERVED")
                .isEqualTo(CostLedgerStatus.RESERVED);

        costLedgerService.complete(id, 7.0, 200L);
        CostLedgerEntry afterComplete = repository.findById(id).orElseThrow();
        assertThat(afterComplete.getStatus()).isEqualTo(CostLedgerStatus.COMPLETED);
        assertThat(afterComplete.getActualUsd()).as("完成时写入的实际花费是 7.0").isEqualTo(7.0);

        // 失败之后重试走新记录
        Long failedId = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 3.0, "n");
        costLedgerService.reserve(failedId, new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0));
        costLedgerService.fail(failedId, 1.0, 50L, "断了");

        Long retryId = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 6.0, "n");
        costLedgerService.reserve(retryId, new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0));
        costLedgerService.complete(retryId, 6.0, 100L);

        CostSummary summary = costLedgerService.summarize(1L, null, null, null);
        assertThat(summary.countByStatus().get(CostLedgerStatus.FAILED)).isEqualTo(1L);
        assertThat(summary.countByStatus().get(CostLedgerStatus.COMPLETED)).as("中断那条 + 重试那条 = 2").isEqualTo(2L);
        assertThat(summary.totalSpentUsd()).as("FAILED 的 1.0 也计入 spent，加上 COMPLETED 的 7.0 + 6.0 = 14.0")
                .isEqualTo(14.0);
    }

    /**
     * 预算守卫累计：CAP 模式，总预算 10.0。
     * 第一条估算 6.0，usable = 10 - 0 - 0 - 10*0 = 10 >= 6，预留成功变 RESERVED。
     * 第二条估算 5.0，usable = 10 - 0 - 6 - 10*0 = 4 < 5，抛 BudgetExceededException，第二条保持 ESTIMATED。
     */
    @Test
    void capBudgetGuardCountsReservedAmounts() {
        Long id1 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 6.0, "n");
        costLedgerService.reserve(id1, new BudgetPolicy(BudgetMode.CAP, 10.0, 0.0));
        assertThat(repository.findById(id1).orElseThrow().getStatus()).isEqualTo(CostLedgerStatus.RESERVED);

        Long id2 = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 5.0, "n");
        assertThatThrownBy(() -> costLedgerService.reserve(id2, new BudgetPolicy(BudgetMode.CAP, 10.0, 0.0)))
                .isInstanceOf(BudgetExceededException.class);

        assertThat(repository.findById(id2).orElseThrow().getStatus())
                .as("CAP 超预算时条目保持 ESTIMATED").isEqualTo(CostLedgerStatus.ESTIMATED);
        assertThat(repository.findById(id1).orElseThrow().getStatus())
                .as("第一条还是 RESERVED").isEqualTo(CostLedgerStatus.RESERVED);
    }

    /**
     * fail 的 note 拼接用 " | " 连接。
     * recordEstimate 传 "init"，fail 传 "boom"，最后应是 "init | boom"。
     */
    @Test
    void failAppendsNoteWithPipeSeparator() {
        Long id = costLedgerService.recordEstimate(1L, "agnes", "m", "generate", 2.0, "init");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0));
        costLedgerService.fail(id, 2.0, 500L, "boom");

        CostLedgerEntry entry = repository.findById(id).orElseThrow();
        assertThat(entry.getStatus()).isEqualTo(CostLedgerStatus.FAILED);
        assertThat(entry.getNote()).as("appendNote 用 ' | ' 连接").isEqualTo("init | boom");
    }
}
