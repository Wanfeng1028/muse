package com.dramafactory.billing;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:costledgertrend;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class CostLedgerTrendDeepTest {

    @Autowired
    private CostLedgerService service;

    @Autowired
    private CostLedgerEntryRepository repository;

    private final BudgetPolicy policy = new BudgetPolicy(BudgetMode.WARN, 1000d, 0d);

    @BeforeEach
    void clean() {
        repository.deleteAll();
    }

    private CostLedgerEntry reload(Long id) {
        return repository.findById(id).orElseThrow();
    }

    @Test
    void threeRecordsAcrossThreeDaysAreAggregatedInAscendingOrder() {
        LocalDate today = LocalDate.now();
        LocalDate yesterday = today.minusDays(1);
        LocalDate dayBefore = today.minusDays(2);

        Long a = service.recordEstimate(1L, "openai", "gpt", "chat", 1.5d, "a");
        Long b = service.recordEstimate(1L, "openai", "gpt", "chat", 2.5d, "b");
        Long c = service.recordEstimate(2L, "anthropic", "claude", "chat", 4.0d, "c");

        CostLedgerEntry ea = reload(a);
        ea.setCreatedAt(dayBefore.atTime(10, 0, 0));
        repository.save(ea);

        CostLedgerEntry eb = reload(b);
        eb.setCreatedAt(yesterday.atTime(10, 0, 0));
        repository.save(eb);

        CostLedgerEntry ec = reload(c);
        ec.setCreatedAt(today.atTime(10, 0, 0));
        repository.save(ec);

        List<CostLedgerService.DailyTrendPoint> trend = service.summarizeTrend(3);

        assertThat(trend).hasSize(3);
        assertThat(trend.get(0).date()).isEqualTo(dayBefore);
        assertThat(trend.get(1).date()).isEqualTo(yesterday);
        assertThat(trend.get(2).date()).isEqualTo(today);

        assertThat(trend.get(0).estimatedUsd()).isEqualTo(1.5d);
        assertThat(trend.get(0).entryCount()).isEqualTo(1L);

        assertThat(trend.get(1).estimatedUsd()).isEqualTo(2.5d);
        assertThat(trend.get(1).entryCount()).isEqualTo(1L);

        assertThat(trend.get(2).estimatedUsd()).isEqualTo(4.0d);
        assertThat(trend.get(2).entryCount()).isEqualTo(1L);
    }

    @Test
    void missingMiddleDayIsPresentWithZeroes() {
        LocalDate today = LocalDate.now();
        LocalDate yesterday = today.minusDays(1);
        LocalDate dayBefore = today.minusDays(2);

        Long a = service.recordEstimate(1L, "openai", "gpt", "chat", 3.0d, "a");
        Long c = service.recordEstimate(1L, "openai", "gpt", "chat", 5.0d, "c");

        CostLedgerEntry ea = reload(a);
        ea.setCreatedAt(dayBefore.atTime(9, 0, 0));
        repository.save(ea);

        CostLedgerEntry ec = reload(c);
        ec.setCreatedAt(today.atTime(9, 0, 0));
        repository.save(ec);

        List<CostLedgerService.DailyTrendPoint> trend = service.summarizeTrend(3);

        assertThat(trend).hasSize(3);
        CostLedgerService.DailyTrendPoint middle = trend.get(1);
        assertThat(middle.date()).isEqualTo(yesterday);
        assertThat(middle.estimatedUsd()).isEqualTo(0d);
        assertThat(middle.spentUsd()).isEqualTo(0d);
        assertThat(middle.entryCount()).isEqualTo(0L);

        assertThat(trend.get(0).estimatedUsd()).isEqualTo(3.0d);
        assertThat(trend.get(2).estimatedUsd()).isEqualTo(5.0d);
    }

    @Test
    void spentOnlyCountsCompletedAndFailed() {
        LocalDate today = LocalDate.now();

        Long completedId = service.recordEstimate(1L, "openai", "gpt", "chat", 1.0d, "c");
        service.reserve(completedId, policy);
        service.complete(completedId, 1.25d, 100L);

        Long failedId = service.recordEstimate(1L, "openai", "gpt", "chat", 2.0d, "f");
        service.reserve(failedId, policy);
        service.fail(failedId, 0d, 200L, "boom");

        Long reservedId = service.recordEstimate(1L, "openai", "gpt", "chat", 3.0d, "r");
        service.reserve(reservedId, policy);

        CostLedgerEntry ec = reload(completedId);
        ec.setCreatedAt(today.atTime(11, 0, 0));
        repository.save(ec);

        CostLedgerEntry ef = reload(failedId);
        ef.setCreatedAt(today.atTime(12, 0, 0));
        repository.save(ef);

        CostLedgerEntry er = reload(reservedId);
        er.setCreatedAt(today.atTime(13, 0, 0));
        repository.save(er);

        List<CostLedgerService.DailyTrendPoint> trend = service.summarizeTrend(1);

        assertThat(trend).hasSize(1);
        CostLedgerService.DailyTrendPoint point = trend.get(0);
        assertThat(point.date()).isEqualTo(today);
        assertThat(point.estimatedUsd()).isEqualTo(6.0d);
        assertThat(point.spentUsd()).isEqualTo(1.25d);
        assertThat(point.entryCount()).isEqualTo(3L);
    }

    @Test
    void daysAreClampedToRange() {
        List<CostLedgerService.DailyTrendPoint> oneDay = service.summarizeTrend(0);
        assertThat(oneDay).hasSize(1);

        List<CostLedgerService.DailyTrendPoint> ninetyDays = service.summarizeTrend(200);
        assertThat(ninetyDays).hasSize(90);
        assertThat(ninetyDays.get(0).date()).isEqualTo(LocalDate.now().minusDays(89));
        assertThat(ninetyDays.get(89).date()).isEqualTo(LocalDate.now());
    }

    @Test
    void midnightBoundarySplitsRecordsAcrossDays() {
        LocalDate today = LocalDate.now();
        LocalDate yesterday = today.minusDays(1);

        Long late = service.recordEstimate(1L, "openai", "gpt", "chat", 7.0d, "late");
        Long early = service.recordEstimate(1L, "openai", "gpt", "chat", 8.0d, "early");

        CostLedgerEntry el = reload(late);
        el.setCreatedAt(yesterday.atTime(23, 59, 59));
        repository.save(el);

        CostLedgerEntry ee = reload(early);
        ee.setCreatedAt(today.atTime(0, 0, 0));
        repository.save(ee);

        List<CostLedgerService.DailyTrendPoint> trend = service.summarizeTrend(2);

        assertThat(trend).hasSize(2);
        assertThat(trend.get(0).date()).isEqualTo(yesterday);
        assertThat(trend.get(0).estimatedUsd()).isEqualTo(7.0d);
        assertThat(trend.get(0).entryCount()).isEqualTo(1L);

        assertThat(trend.get(1).date()).isEqualTo(today);
        assertThat(trend.get(1).estimatedUsd()).isEqualTo(8.0d);
        assertThat(trend.get(1).entryCount()).isEqualTo(1L);
    }
}
