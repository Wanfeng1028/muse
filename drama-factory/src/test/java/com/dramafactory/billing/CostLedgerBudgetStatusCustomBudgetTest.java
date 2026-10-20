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
        "spring.datasource.url=jdbc:h2:mem:costledgerbudget2;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "drama.billing.budget-total-usd=200"
})
class CostLedgerBudgetStatusCustomBudgetTest {

    @Autowired
    private CostLedgerService costLedgerService;

    @Autowired
    private CostLedgerEntryRepository repository;

    @BeforeEach
    void setUp() {
        repository.deleteAll();
    }

    @Test
    void emptyLedgerUsesCustomBudgetTotal() {
        CostLedgerService.BudgetStatus status = costLedgerService.budgetStatus();

        assertThat(status.budgetTotalUsd()).isCloseTo(200d, within(1e-9));
        assertThat(status.spentUsd()).isCloseTo(0d, within(1e-9));
        assertThat(status.reservedUsd()).isCloseTo(0d, within(1e-9));
        assertThat(status.usableUsd()).isCloseTo(180d, within(1e-9));
        assertThat(status.utilizationPct()).isCloseTo(0d, within(1e-9));
    }

    @Test
    void customBudgetScalesUsable() {
        Long completed = costLedgerService.recordEstimate(1L, "OPENAI", "gpt-4o", "req-1", 1d, "USD");
        costLedgerService.reserve(completed, new BudgetPolicy(BudgetMode.WARN, 10000d, 0d));
        costLedgerService.complete(completed, 40d, 1L);

        CostLedgerService.BudgetStatus status = costLedgerService.budgetStatus();

        assertThat(status.budgetTotalUsd()).isCloseTo(200d, within(1e-9));
        assertThat(status.spentUsd()).isCloseTo(40d, within(1e-9));
        assertThat(status.usableUsd()).isCloseTo(200d - 40d - 0d - 20d, within(1e-9));
        assertThat(status.utilizationPct()).isCloseTo(20d, within(1e-9));
    }
}
