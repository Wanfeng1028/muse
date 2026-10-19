package com.dramafactory.billing;

/**
 * 预算策略配置。
 *
 * @param mode          预算模式
 * @param budgetTotalUsd 总预算（美元）
 * @param reservePct    预留占用的比例（会被截断到 [0, 0.9]）
 */
public record BudgetPolicy(BudgetMode mode, double budgetTotalUsd, double reservePct) {
}
