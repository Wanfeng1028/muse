package com.dramafactory.service.byok;

import com.dramafactory.service.video.VideoProvider;

/**
 * 图片生成提供方抽象接口（BYOK）。
 */
public interface ImageProvider {

    /** 提供方侧任务状态。 */
    enum RemoteStatus {
        /** 排队中 */ QUEUED,
        /** 生成中 */ PROCESSING,
        /** 已完成 */ SUCCEEDED,
        /** 已失败 */ FAILED
    }

    /** 提交结果：提供方任务 ID。 */
    record SubmitResult(String taskId) {}

    /**
     * 轮询结果。
     *
     * @param status       提供方侧任务状态
     * @param imageUrl     生成完成后的图片地址，未完成或失败时为 null
     * @param errorMessage 失败原因，成功或未完成时为 null
     * @param progress     进度百分比（0-100）
     */
    record PollResult(RemoteStatus status, String imageUrl, String errorMessage, int progress) {}

    /**
     * 连接自检结果。detail 为面向用户的说明文案，绝不包含任何密钥原文或片段；
     * status=OK 之外不得出现"成功"字样。
     */
    record ConnectivityResult(VideoProvider.ConnectivityStatus status, String detail) {}

    /**
     * 提交图片生成任务。
     *
     * @param apiKey   通道管理卡片 key，可空（实现内按卡片→设置→surrogate 顺序解析）
     * @param apiBase API 基地址，可空（实现内用默认值）
     * @param modelId  模型 ID（取用户在通道管理配置的模型）
     * @param prompt   提示词
     * @param size     尺寸，如 1024*1024
     * @return 提交结果
     */
    SubmitResult submit(String apiKey, String apiBase, String modelId, String prompt, String size);

    /**
     * 轮询任务状态。
     *
     * @param apiKey   通道管理卡片 key，可空
     * @param apiBase  API 基地址，可空
     * @param taskId   提供方任务 ID
     * @return 轮询结果
     */
    PollResult poll(String apiKey, String apiBase, String taskId);

    /**
     * 连接自检（零费用）。默认为不支持，各提供方按需重写。
     */
    default ConnectivityResult probe(String apiKey, String apiBase) {
        return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNSUPPORTED, "该提供方暂不支持连接自检");
    }

    /** 返回提供方名称，例如 "dashscope-image"。 */
    String name();
}
