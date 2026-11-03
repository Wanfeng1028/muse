package com.dramafactory.model;

/**
 * 视频生成任务状态枚举。
 * 用于标识短剧分镜视频生成任务在其生命周期中的当前状态。
 */
public enum VideoTaskStatus {

    /** 待提交：任务已创建但尚未提交到生成服务 */
    PENDING("待提交"),

    /** 生成中：任务已提交，正在生成视频 */
    PROCESSING("生成中"),

    /** 已完成：视频生成成功并已获取结果 */
    DONE("已完成"),

    /** 失败：视频生成过程中出现错误 */
    FAILED("失败");

    /** 状态的中文标签，用于前端展示 */
    private final String label;

    /**
     * 构造枚举实例。
     *
     * @param label 中文标签
     */
    VideoTaskStatus(String label) {
        this.label = label;
    }

    /**
     * 获取状态的中文标签。
     *
     * @return 中文标签
     */
    public String getLabel() {
        return label;
    }
}
