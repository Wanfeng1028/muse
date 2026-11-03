package com.dramafactory.billing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:costledgerbudget;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class CostLedgerBudgetStatusDeepTest {

    @Autowired
    private CostLedgerService costLedgerService;

    @Autowired
    private CostLedgerEntryRepository repository;

    @BeforeEach
    void setUp() {
        repository.deleteAll();
    }

    @Test
    void emptyLedgerReportsDefaults() {
        CostLedgerService.BudgetStatus status = costLedgerService.budgetStatus();

        assertThat(status.budgetTotalUsd()).isCloseTo(100d, within(1e-9));
        assertThat(status.spentUsd()).isCloseTo(0d, within(1e-9));
        assertThat(status.reservedUsd()).isCloseTo(0d, within(1e-9));
        assertThat(status.usableUsd()).isCloseTo(90d, within(1e-9));
        assertThat(status.utilizationPct()).isCloseTo(0d, within(1e-9));
        assertThat(status.mode()).isEqualTo("WARN");
        assertThat(status.enabled()).isTrue();
    }

    @Test
    void completedAndReservedEntriesAreAggregated() {
        Long first = costLedgerService.recordEstimate(1L, "OPENAI", "gpt-4o", "req-1", 1d, "USD");
        costLedgerService.reserve(first, new BudgetPolicy(BudgetMode.WARN, 10000d, 0d));
        costLedgerService.complete(first, 10d, 1L);

        Long second = costLedgerService.recordEstimate(1L, "OPENAI", "gpt-4o", "req-2", 1d, "USD");
        costLedgerService.reserve(second, new BudgetPolicy(BudgetMode.WARN, 10000d, 0d));
        costLedgerService.complete(second, 20d, 1L);

        Long third = costLedgerService.recordEstimate(1L, "OPENAI", "gpt-4o", "req-3", 5d, "USD");
        costLedgerService.reserve(third, new BudgetPolicy(BudgetMode.WARN, 10000d, 0d));

        CostLedgerService.BudgetStatus status = costLedgerService.budgetStatus();

        assertThat(status.budgetTotalUsd()).isCloseTo(100d, within(1e-9));
        assertThat(status.spentUsd()).isCloseTo(30d, within(1e-9));
        assertThat(status.reservedUsd()).isCloseTo(5d, within(1e-9));
        assertThat(status.usableUsd()).isCloseTo(55d, within(1e-9));
        assertThat(status.utilizationPct()).isCloseTo(30d, within(1e-9));
    }

    @Test
    void failedCountsTowardSpentAndRefundedCountsTowardNothing() {
        Long completed = costLedgerService.recordEstimate(1L, "OPENAI", "gpt-4o", "req-1", 1d, "USD");
        costLedgerService.reserve(completed, new BudgetPolicy(BudgetMode.WARN, 10000d, 0d));
        costLedgerService.complete(completed, 10d, 1L);

        Long failed = costLedgerService.recordEstimate(1L, "OPENAI", "gpt-4o", "req-2", 1d, "USD");
        costLedgerService.reserve(failed, new BudgetPolicy(BudgetMode.WARN, 10000d, 0d));
        costLedgerService.fail(failed, 7d, 1L, "boom");

        Long refunded = costLedgerService.recordEstimate(1L, "OPENAI", "gpt-4o", "req-3", 3d, "USD");
        costLedgerService.reserve(refunded, new BudgetPolicy(BudgetMode.WARN, 10000d, 0d));
        costLedgerService.refund(refunded);

        CostLedgerService.BudgetStatus status = costLedgerService.budgetStatus();

        assertThat(status.spentUsd()).isCloseTo(17d, within(1e-9));
        assertThat(status.reservedUsd()).isCloseTo(0d, within(1e-9));
        assertThat(status.usableUsd()).isCloseTo(100d - 17d - 0d - 10d, within(1e-9));
    }

    @Test
    void modeAndEnabledArePassedThrough() {
        CostLedgerService.BudgetStatus status = costLedgerService.budgetStatus();

        assertThat(status.mode()).isEqualTo("WARN");
        assertThat(status.enabled()).isTrue();
    }
}
