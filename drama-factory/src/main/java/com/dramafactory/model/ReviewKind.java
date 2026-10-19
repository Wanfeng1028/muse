package com.dramafactory.model;

/**
 * 审核对象类型：剧本、分镜。
 */
public enum ReviewKind {

    SCRIPT("剧本"),
    BOARD("分镜");

    private final String label;

    ReviewKind(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
