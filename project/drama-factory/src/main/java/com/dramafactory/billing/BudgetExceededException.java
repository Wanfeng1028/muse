package com.dramafactory.billing;

/**
 * 预留成本超出预算时抛出。
 */
public class BudgetExceededException extends RuntimeException {

    private final double estimatedUsd;
    private final double usableUsd;

    /**
     * 仅带消息构造。
     */
    public BudgetExceededException(String message) {
        super(message);
        this.estimatedUsd = 0d;
        this.usableUsd = 0d;
    }

    /**
     * 带估算金额与可用预算构造。
     */
    public BudgetExceededException(String message, double estimatedUsd, double usableUsd) {
        super(message);
        this.estimatedUsd = estimatedUsd;
        this.usableUsd = usableUsd;
    }

    public double getEstimatedUsd() {
        return estimatedUsd;
    }

    public double getUsableUsd() {
        return usableUsd;
    }
}
