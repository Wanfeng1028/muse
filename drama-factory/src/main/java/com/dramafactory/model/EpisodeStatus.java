package com.dramafactory.model;

/**
 * 剧集状态枚举。
 */
public enum EpisodeStatus {

    /** 草稿：剧集刚创建，尚未编写剧本 */
    DRAFT,

    /** 已编剧：已生成场景剧本，但尚未生成视频素材 */
    SCRIPTED,

    /** 已生成：视频素材已生成完成 */
    GENERATED,

    /** 已审阅：剧集已通过审阅，可发布 */
    REVIEWED
}
