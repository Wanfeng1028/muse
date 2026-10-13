package com.dramafactory.model;

/**
 * 运镜方式枚举。
 * 描述短剧分镜中镜头运动的类型。
 */
public enum CameraMove {

    /** 固定机位 */
    GU_DING("固定机位"),

    /** 推镜头 */
    TUI("推镜头"),

    /** 拉镜头 */
    LA("拉镜头"),

    /** 摇镜头 */
    YAO("摇镜头"),

    /** 移镜头 */
    YI("移镜头"),

    /** 跟镜头 */
    GEN("跟镜头"),

    /** 升降镜头 */
    SHENG_JIANG("升降");

    /** 运镜的中文标签 */
    private final String label;

    /**
     * 构造器。
     *
     * @param label 中文标签
     */
    CameraMove(String label) {
        this.label = label;
    }

    /**
     * 获取中文标签。
     *
     * @return 中文标签
     */
    public String getLabel() {
        return label;
    }

    /**
     * 根据中文标签解析运镜枚举，忽略大小写与首尾空白。
     *
     * @param label 中文标签
     * @return 匹配的枚举；若无匹配返回 null
     */
    public static CameraMove fromLabel(String label) {
        if (label == null) {
            return null;
        }
        String trimmed = label.trim();
        for (CameraMove move : values()) {
            if (move.label.equalsIgnoreCase(trimmed)) {
                return move;
            }
        }
        return null;
    }
}
