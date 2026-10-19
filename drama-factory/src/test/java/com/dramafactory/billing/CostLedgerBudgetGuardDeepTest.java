package com.dramafactory.billing;

import java.time.LocalDateTime;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:costledgerbudgetguard;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class CostLedgerBudgetGuardDeepTest {

    @Autowired
    private CostLedgerService costLedgerService;

    @Autowired
    private CostLedgerEntryRepository repository;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAll();
    }

    @Test
    void reserve_reservePctAboveOne_clampedToPointNine() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.WARN, 100.0, 1.5);

        Long idEleven = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 11.0, "n11");
        costLedgerService.reserve(idEleven, policy);
        CostLedgerEntry eleven = repository.findById(idEleven).orElseThrow();
        assertThat(eleven.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(eleven.getNote()).contains("[BUDGET-WARN]");

        // 清库：前一条目的冻结金额会占用 usable，边界用例需在干净预算下验证
        repository.deleteAll();

        Long idTen = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 10.0, "n10");
        costLedgerService.reserve(idTen, policy);
        CostLedgerEntry ten = repository.findById(idTen).orElseThrow();
        assertThat(ten.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(ten.getNote()).doesNotContain("[BUDGET-WARN]");
    }

    @Test
    void reserve_negativeReservePct_clampedToZero() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.WARN, 100.0, -0.2);

        Long id = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 100.0, "n");
        costLedgerService.reserve(id, policy);
        CostLedgerEntry entry = repository.findById(id).orElseThrow();
        assertThat(entry.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(entry.getNote()).doesNotContain("[BUDGET-WARN]");
    }

    @Test
    void reserve_nullPolicy_defaultsToWarnZeroBudget() {
        Long idOne = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 1.0, "n1");
        costLedgerService.reserve(idOne, null);
        CostLedgerEntry one = repository.findById(idOne).orElseThrow();
        assertThat(one.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(one.getNote()).contains("[BUDGET-WARN]");

        // 清库：前一条目的冻结金额会占用 usable，边界用例需在干净预算下验证
        repository.deleteAll();

        Long idZero = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 0.0, "n0");
        costLedgerService.reserve(idZero, null);
        CostLedgerEntry zero = repository.findById(idZero).orElseThrow();
        assertThat(zero.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(zero.getNote()).doesNotContain("[BUDGET-WARN]");
    }

    @Test
    void reserve_estimatedEqualsUsable_noWarning() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.WARN, 50.0, 0.0);

        Long id = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 50.0, "n");
        costLedgerService.reserve(id, policy);
        CostLedgerEntry entry = repository.findById(id).orElseThrow();
        assertThat(entry.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(entry.getNote()).doesNotContain("[BUDGET-WARN]");
    }

    @Test
    void reserve_spentAndReservedReduceUsable() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.CAP, 100.0, 0.0);

        Long idA = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 30.0, "a");
        costLedgerService.reserve(idA, policy);
        costLedgerService.complete(idA, 30.0, 100L);

        Long idB = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 20.0, "b");
        costLedgerService.reserve(idB, policy);

        Long idC = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 51.0, "c");
        assertThatThrownBy(() -> costLedgerService.reserve(idC, policy))
                .isInstanceOf(BudgetExceededException.class)
                .satisfies(ex -> {
                    BudgetExceededException bee = (BudgetExceededException) ex;
                    assertThat(bee.getEstimatedUsd()).isEqualTo(51.0);
                    assertThat(bee.getUsableUsd()).isEqualTo(50.0);
                });
        assertThat(repository.findById(idC).orElseThrow().getStatus()).isEqualTo(CostLedgerStatus.ESTIMATED);

        Long idD = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 50.0, "d");
        costLedgerService.reserve(idD, policy);
        assertThat(repository.findById(idD).orElseThrow().getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
    }

    @Test
    void reserve_failedEntryActualCountsAsSpent() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.CAP, 100.0, 0.0);

        Long idA = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 10.0, "a");
        costLedgerService.reserve(idA, policy);
        costLedgerService.fail(idA, 40.0, 100L, "boom");

        Long idB = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 61.0, "b");
        assertThatThrownBy(() -> costLedgerService.reserve(idB, policy))
                .isInstanceOf(BudgetExceededException.class)
                .satisfies(ex -> {
                    BudgetExceededException bee = (BudgetExceededException) ex;
                    assertThat(bee.getUsableUsd()).isEqualTo(60.0);
                });
    }

    @Test
    void refund_releasesReservedBudget() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.CAP, 100.0, 0.0);

        Long idA = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 40.0, "a");
        costLedgerService.reserve(idA, policy);
        costLedgerService.refund(idA);
        assertThat(repository.findById(idA).orElseThrow().getStatus()).isEqualTo(CostLedgerStatus.REFUNDED);

        Long idB = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 100.0, "b");
        costLedgerService.reserve(idB, policy);
        assertThat(repository.findById(idB).orElseThrow().getStatus()).isEqualTo(CostLedgerStatus.RESERVED);

        CostSummary summary = costLedgerService.summarize(1L, null, null, null);
        assertThat(summary.totalReservedUsd()).isEqualTo(100.0);
    }

    @Test
    void capMode_exceptionCarriesAmounts() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.CAP, 80.0, 0.25);

        Long id = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 61.0, "n");
        assertThatThrownBy(() -> costLedgerService.reserve(id, policy))
                .isInstanceOf(BudgetExceededException.class)
                .satisfies(ex -> {
                    BudgetExceededException bee = (BudgetExceededException) ex;
                    assertThat(bee.getEstimatedUsd()).isEqualTo(61.0);
                    assertThat(bee.getUsableUsd()).isEqualTo(60.0);
                });
    }

    @Test
    void recordEstimate_negativeAmount_throwsAndNoSideEffect() {
        long before = repository.count();
        assertThatThrownBy(() -> costLedgerService.recordEstimate(1L, "agnes", "m", "op", -0.01, "n"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(repository.count()).isEqualTo(before);
    }

    @Test
    void illegalTransitions_fullMatrix() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0);

        Long completedId = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 5.0, "c");
        costLedgerService.reserve(completedId, policy);
        costLedgerService.complete(completedId, 5.0, 100L);
        assertThatThrownBy(() -> costLedgerService.complete(completedId, 5.0, 100L))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> costLedgerService.refund(completedId))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> costLedgerService.fail(completedId, 5.0, 100L, "x"))
                .isInstanceOf(IllegalStateException.class);

        Long refundedId = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 5.0, "r");
        costLedgerService.reserve(refundedId, policy);
        costLedgerService.refund(refundedId);
        assertThatThrownBy(() -> costLedgerService.refund(refundedId))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> costLedgerService.complete(refundedId, 5.0, 100L))
                .isInstanceOf(IllegalStateException.class);

        Long estimatedId = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 5.0, "e");
        assertThatThrownBy(() -> costLedgerService.complete(estimatedId, 5.0, 100L))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> costLedgerService.fail(estimatedId, 5.0, 100L, "x"))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> costLedgerService.refund(estimatedId))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void summarize_timeBoundsAreInclusive() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0);
        LocalDateTime t = LocalDateTime.of(2024, 5, 15, 12, 0, 0);

        createVisibleEntry(1L, "agnes", 5.0, t, policy);
        createVisibleEntry(1L, "agnes", 6.0, t.minusHours(1), policy);
        createVisibleEntry(1L, "agnes", 7.0, t.plusHours(1), policy);

        CostSummary exactlyT = costLedgerService.summarize(null, null, t, t);
        assertThat(exactlyT.entryCount()).isEqualTo(1);

        CostSummary range = costLedgerService.summarize(null, null, t.minusHours(1), t.plusHours(1));
        assertThat(range.entryCount()).isEqualTo(3);
    }

    @Test
    void summarize_projectAndProviderCombinedFilter() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0);

        Long a = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 5.0, "a");
        costLedgerService.reserve(a, policy);
        Long b = costLedgerService.recordEstimate(1L, "qwen", "m", "op", 6.0, "b");
        costLedgerService.reserve(b, policy);
        Long c = costLedgerService.recordEstimate(2L, "agnes", "m", "op", 7.0, "c");
        costLedgerService.reserve(c, policy);

        assertThat(costLedgerService.summarize(1L, "agnes", null, null).entryCount()).isEqualTo(1);
        assertThat(costLedgerService.summarize(1L, null, null, null).entryCount()).isEqualTo(2);
        assertThat(costLedgerService.summarize(null, "agnes", null, null).entryCount()).isEqualTo(2);
    }

    @Test
    void summarize_emptyTable_zerosAndAllStatusesPresent() {
        CostSummary summary = costLedgerService.summarize(null, null, null, null);

        assertThat(summary.entryCount()).isEqualTo(0);
        assertThat(summary.totalEstimatedUsd()).isEqualTo(0.0);
        assertThat(summary.totalReservedUsd()).isEqualTo(0.0);
        assertThat(summary.totalSpentUsd()).isEqualTo(0.0);

        assertThat(summary.countByStatus().get(CostLedgerStatus.ESTIMATED)).isEqualTo(0L);
        assertThat(summary.countByStatus().get(CostLedgerStatus.RESERVED)).isEqualTo(0L);
        assertThat(summary.countByStatus().get(CostLedgerStatus.COMPLETED)).isEqualTo(0L);
        assertThat(summary.countByStatus().get(CostLedgerStatus.FAILED)).isEqualTo(0L);
        assertThat(summary.countByStatus().get(CostLedgerStatus.REFUNDED)).isEqualTo(0L);
    }

    @Test
    void summarize_spentIgnoresNullActual() {
        BudgetPolicy policy = new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0);

        Long id = costLedgerService.recordEstimate(1L, "agnes", "m", "op", 5.0, "n");
        costLedgerService.reserve(id, policy);

        CostLedgerEntry entry = repository.findById(id).orElseThrow();
        entry.setStatus(CostLedgerStatus.COMPLETED);
        repository.save(entry);

        CostSummary summary = costLedgerService.summarize(null, null, null, null);
        assertThat(summary.totalSpentUsd()).isEqualTo(0.0);
    }

    private Long createVisibleEntry(Long projectId, String provider, double estimatedUsd,
                                    LocalDateTime createdAt, BudgetPolicy policy) {
        CostLedgerEntry entry = new CostLedgerEntry();
        entry.setProjectId(projectId);
        entry.setProvider(provider);
        entry.setModel("m");
        entry.setOperation("op");
        entry.setEstimatedUsd(estimatedUsd);
        entry.setStatus(CostLedgerStatus.ESTIMATED);
        entry.setNote("n");
        entry.setCreatedAt(createdAt);
        CostLedgerEntry saved = repository.save(entry);

        costLedgerService.reserve(saved.getId(), policy);
        costLedgerService.complete(saved.getId(), estimatedUsd, 100L);
        return saved.getId();
    }
}