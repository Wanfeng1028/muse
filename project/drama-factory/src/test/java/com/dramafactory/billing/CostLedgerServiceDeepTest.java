package com.dramafactory.billing;

import com.dramafactory.billing.CostLedgerEntry;
import com.dramafactory.billing.CostLedgerEntryRepository;
import com.dramafactory.billing.CostLedgerStatus;
import com.dramafactory.billing.CostLedgerService;
import com.dramafactory.billing.CostSummary;
import com.dramafactory.billing.BudgetExceededException;
import com.dramafactory.billing.BudgetMode;
import com.dramafactory.billing.BudgetPolicy;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * CostLedgerService 深度测试，直连 repository 验证状态流转与预算策略。
 * 使用独立 H2 内存库避免跨测试污染。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:costledgerdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class CostLedgerServiceDeepTest {

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
    void recordEstimate_reserve_complete_transitionsAndRecordsActuals() {
        Long id = costLedgerService.recordEstimate(1L, "agnes", "gpt-x", "generate", 10.0, "init");

        CostLedgerEntry estimated = reload(id);
        assertThat(estimated.getStatus()).isEqualTo(CostLedgerStatus.ESTIMATED);
        assertThat(estimated.getEstimatedUsd()).isEqualTo(10.0);
        assertThat(estimated.getProvider()).isEqualTo("agnes");

        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0));
        assertThat(reload(id).getStatus()).isEqualTo(CostLedgerStatus.RESERVED);

        costLedgerService.complete(id, 9.5, 1234L);

        CostLedgerEntry completed = reload(id);
        assertThat(completed.getStatus()).isEqualTo(CostLedgerStatus.COMPLETED);
        assertThat(completed.getActualUsd()).isEqualTo(9.5);
        assertThat(completed.getDurationMs()).isEqualTo(1234L);
    }

    @Test
    void reserve_onAlreadyReservedEntry_throwsIllegalStateException() {
        Long id = costLedgerService.recordEstimate(1L, "agnes", "gpt-x", "generate", 10.0, "init");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0));

        assertThatThrownBy(() -> costLedgerService.reserve(id,
                new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0)))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void complete_onEstimatedEntry_throwsIllegalStateException() {
        Long id = costLedgerService.recordEstimate(1L, "agnes", "gpt-x", "generate", 10.0, "init");

        assertThatThrownBy(() -> costLedgerService.complete(id, 5.0, 100L))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void refund_movesReservedToRefunded() {
        Long id = costLedgerService.recordEstimate(1L, "agnes", "gpt-x", "generate", 10.0, "init");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0));

        costLedgerService.refund(id);

        assertThat(reload(id).getStatus()).isEqualTo(CostLedgerStatus.REFUNDED);
    }

    @Test
    void fail_movesReservedToFailedAndAppendsNote() {
        Long id = costLedgerService.recordEstimate(1L, "agnes", "gpt-x", "generate", 10.0, "init");
        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 100.0, 0.0));

        costLedgerService.fail(id, 2.0, 500L, "boom");

        CostLedgerEntry failed = reload(id);
        assertThat(failed.getStatus()).isEqualTo(CostLedgerStatus.FAILED);
        assertThat(failed.getNote()).contains("boom");
    }

    @Test
    void reserve_capModeOverBudget_throwsBudgetExceededAndStaysEstimated() {
        Long id = costLedgerService.recordEstimate(1L, "agnes", "gpt-x", "generate", 10.0, "init");

        assertThatThrownBy(() -> costLedgerService.reserve(id,
                new BudgetPolicy(BudgetMode.CAP, 5.0, 0.0)))
                .isInstanceOf(BudgetExceededException.class);

        assertThat(reload(id).getStatus()).isEqualTo(CostLedgerStatus.ESTIMATED);
    }

    @Test
    void reserve_warnModeOverBudget_reservesAndAppendsBudgetWarn() {
        Long id = costLedgerService.recordEstimate(1L, "agnes", "gpt-x", "generate", 10.0, "init");

        costLedgerService.reserve(id, new BudgetPolicy(BudgetMode.WARN, 5.0, 0.0));

        CostLedgerEntry reserved = reload(id);
        assertThat(reserved.getStatus()).isEqualTo(CostLedgerStatus.RESERVED);
        assertThat(reserved.getNote()).contains("BUDGET-WARN");
    }

    @Test
    void summarize_aggregatesAcrossProvidersAndStatuses() {
        // agnes 提供商：一条 COMPLETED，一条 ESTIMATED
        Long agnesCompleted = costLedgerService.recordEstimate(2L, "agnes", "gpt-x", "generate", 10.0, "a1");
        costLedgerService.reserve(agnesCompleted, new BudgetPolicy(BudgetMode.WARN, 1000.0, 0.0));
        costLedgerService.complete(agnesCompleted, 8.0, 100L);

        Long agnesEstimated = costLedgerService.recordEstimate(2L, "agnes", "gpt-x", "generate", 4.0, "a2");

        // 另一提供商，不应被计入
        costLedgerService.recordEstimate(2L, "other", "model-y", "generate", 7.0, "b1");

        CostSummary summary = costLedgerService.summarize(null, "agnes", null, null);

        assertThat(summary.entryCount()).isEqualTo(2L);
        assertThat(summary.totalEstimatedUsd()).isEqualTo(14.0);
        assertThat(summary.totalSpentUsd()).isEqualTo(8.0);
        assertThat(summary.countByStatus()).containsEntry(CostLedgerStatus.COMPLETED, 1L);
        assertThat(summary.countByStatus()).containsEntry(CostLedgerStatus.ESTIMATED, 1L);

        // 确认第二条仍为 ESTIMATED 且未计入 spent
        assertThat(reload(agnesEstimated).getStatus()).isEqualTo(CostLedgerStatus.ESTIMATED);

        // 保险：全部条目数量应大于 agnes 聚合条目数量
        List<CostLedgerEntry> all = repository.findAll();
        assertThat(all).hasSizeGreaterThan((int) summary.entryCount());
    }
}
