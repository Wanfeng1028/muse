package com.dramafactory.model;

/**
 * 成片剪辑状态枚举。
 * 用于标识一部成片（FinalCut）当前所处的剪辑处理阶段。
 */
public enum FinalCutStatus {

    /** 剪辑中 */
    BUILDING("剪辑中"),

    /** 已完成 */
    READY("已完成"),

    /** 失败 */
    FAILED("失败");

    /** 状态对应的中文展示文案 */
    private final String label;

    /**
     * 构造器。
     *
     * @param label 中文展示文案
     */
    FinalCutStatus(String label) {
        this.label = label;
    }

    /**
     * 获取状态的中文展示文案。
     *
     * @return 中文文案
     */
    public String getLabel() {
        return label;
    }
}
