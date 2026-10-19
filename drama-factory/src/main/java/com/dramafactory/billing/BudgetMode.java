package com.dramafactory.billing;

/**
 * 预算模式：WARN 仅告警，CAP 超预算抛异常。
 */
public enum BudgetMode {
    /** 仅记录告警，继续预留 */
    WARN,
    /** 超预算直接抛出 BudgetExceededException */
    CAP
}
