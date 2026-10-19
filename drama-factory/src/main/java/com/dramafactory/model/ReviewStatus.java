package com.dramafactory.model;

/**
 * 审核状态：剧本两级审核、分镜一级审核共用。
 */
public enum ReviewStatus {

    DRAFT("草稿"),
    PENDING_L1("待一审"),
    PENDING_L2("待二审"),
    PENDING("待审核"),
    APPROVED("通过"),
    REJECTED("驳回");

    private final String label;

    ReviewStatus(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
