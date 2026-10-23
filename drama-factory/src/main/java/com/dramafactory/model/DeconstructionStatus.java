package com.dramafactory.model;

/**
 * 视频拆解任务状态枚举。
 */
public enum DeconstructionStatus {

    /** 待处理 */
    PENDING,

    /** 处理中 */
    RUNNING,

    /** 已完成 */
    DONE,

    /** 失败 */
    FAILED
}
