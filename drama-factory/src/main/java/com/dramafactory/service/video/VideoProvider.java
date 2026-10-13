package com.dramafactory.service.video;

import com.dramafactory.model.Shot;

/**
 * 视频提供方抽象接口。
 * 用于屏蔽不同视频生成服务（如 agnes、mock）的差异，
 * 上层通过统一契约提交任务并轮询状态。
 */
public interface VideoProvider {

    /**
     * 提供方侧任务状态。
     */
    enum RemoteStatus {
        /** 排队中 */
        QUEUED,
        /** 生成中 */
        PROCESSING,
        /** 已完成 */
        COMPLETED,
        /** 已失败 */
        FAILED
    }

    /**
     * 轮询结果。
     *
     * @param status       提供方侧任务状态
     * @param videoUrl     生成完成后的视频地址，未完成或失败时为 null
     * @param errorMessage 失败原因，成功或未完成时为 null
     * @param progress     进度百分比（0-100）
     */
    record ProbeResult(RemoteStatus status, String videoUrl, String errorMessage, int progress) {
    }

    /**
     * 提交视频生成任务。
     * prompt 优先取 {@link Shot#getVideoPrompt()}，为空时使用 {@link Shot#getDescription()}
     * 拼接景别与运镜的中文名。
     *
     * @param shot    分镜实体
     * @param seconds 目标视频时长（秒）
     * @return 提供方任务 ID
     */
    String submit(Shot shot, int seconds);

    /**
     * 轮询任务状态。
     *
     * @param providerTaskId 提供方任务 ID
     * @return 轮询结果
     */
    ProbeResult poll(String providerTaskId);

    /**
     * 返回提供方名称，例如 "agnes"、"mock"。
     *
     * @return 提供方名
     */
    String name();
}
