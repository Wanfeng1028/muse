package com.dramafactory.billing;

import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 成本账本条目仓储。
 */
public interface CostLedgerEntryRepository extends JpaRepository<CostLedgerEntry, Long> {

    /** 按项目查询条目。 */
    List<CostLedgerEntry> findByProjectId(Long projectId);

    /** 按供应商查询条目。 */
    List<CostLedgerEntry> findByProvider(String provider);

    /** 按状态查询条目。 */
    List<CostLedgerEntry> findByStatus(CostLedgerStatus status);

    /** 按创建时间区间查询条目。 */
    List<CostLedgerEntry> findByCreatedAtBetween(LocalDateTime from, LocalDateTime to);
}
