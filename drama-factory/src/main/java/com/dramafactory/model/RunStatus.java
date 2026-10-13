package com.dramafactory.model;

/**
 * Harness Run 的整体状态。
 */
public enum RunStatus {
    DRAFT("草稿"),
    PLANNED("已规划"),
    RUNNING("执行中"),
    PAUSED("已暂停"),
    WAITING_APPROVAL("等待审批"),
    SUCCEEDED("成功"),
    FAILED("失败"),
    CANCELLED("已取消");

    private final String label;

    RunStatus(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
