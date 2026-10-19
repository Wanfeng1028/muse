package com.dramafactory.billing;

/**
 * 成本账本条目的状态。
 */
public enum CostLedgerStatus {
    /** 已估算，尚未占用预算 */
    ESTIMATED,
    /** 已预留，冻结了估算金额 */
    RESERVED,
    /** 已完成，记录了实际花费 */
    COMPLETED,
    /** 已失败，记录了实际花费 */
    FAILED,
    /** 已退款，释放了冻结金额 */
    REFUNDED
}
