package com.dramafactory.billing;

import java.util.Map;

/**
 * 成本汇总结果：条目数、估算/冻结/已花费金额、按状态计数。
 *
 * @param entryCount        条目总数
 * @param totalEstimatedUsd 估算金额合计
 * @param totalReservedUsd  已冻结金额合计（RESERVED 条目的估算金额）
 * @param totalSpentUsd     已花费金额合计（COMPLETED/FAILED 条目的实际金额）
 * @param countByStatus     按状态分组的条目数
 */
public record CostSummary(long entryCount,
                          double totalEstimatedUsd,
                          double totalReservedUsd,
                          double totalSpentUsd,
                          Map<CostLedgerStatus, Long> countByStatus) {
}
