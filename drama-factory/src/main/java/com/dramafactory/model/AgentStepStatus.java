package com.dramafactory.model;

/**
 * Agent 单个步骤的执行状态。
 */
public enum AgentStepStatus {
    PENDING("待执行"),
    RUNNING("执行中"),
    SUCCEEDED("成功"),
    FAILED("失败"),
    SKIPPED("已跳过"),
    CANCELLED("已取消");

    private final String label;

    AgentStepStatus(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
