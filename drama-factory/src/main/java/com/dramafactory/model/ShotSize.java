package com.dramafactory.model;

/**
 * 景别枚举。
 * 用于描述镜头画面的取景范围，从特写到远景逐级拉远。
 */
public enum ShotSize {

    /** 特写 */
    TE_XIE("特写"),

    /** 近景 */
    JIN_JING("近景"),

    /** 中景 */
    ZHONG_JING("中景"),

    /** 全景 */
    QUAN_JING("全景"),

    /** 远景 */
    YUAN_JING("远景");

    /** 中文标签 */
    private final String label;

    /**
     * 构造器。
     *
     * @param label 中文标签
     */
    ShotSize(String label) {
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
     * 根据中文标签查找对应的景别。
     *
     * @param label 中文标签
     * @return 匹配的景别枚举
     * @throws IllegalArgumentException 找不到匹配项时抛出
     */
    public static ShotSize fromLabel(String label) {
        for (ShotSize size : values()) {
            if (size.label.equals(label)) {
                return size;
            }
        }
        throw new IllegalArgumentException("未知的景别标签: " + label);
    }
}
