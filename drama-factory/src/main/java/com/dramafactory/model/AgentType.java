package com.dramafactory.model;

/**
 * Harness 中的 Agent 类型。
 */
public enum AgentType {
    SCRIPT("编剧"),
    BOARD("分镜"),
    VIDEO("视频生成"),
    EDIT("剪辑"),
    QC("质检");

    private final String label;

    AgentType(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
