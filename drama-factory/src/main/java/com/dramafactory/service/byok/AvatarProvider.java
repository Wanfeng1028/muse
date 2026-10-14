package com.dramafactory.service.byok;

import com.dramafactory.service.video.VideoProvider;

/**
 * 数字人（口播视频）提供方抽象接口（BYOK）。
 */
public interface AvatarProvider {

    /** 提供方侧任务状态。 */
    enum RemoteStatus {
        /** 排队中 */ QUEUED,
        /** 生成中 */ PROCESSING,
        /** 已完成 */ SUCCEEDED,
        /** 已失败 */ FAILED
    }

    /** 提交结果：提供方 talk ID。 */
    record SubmitResult(String talkId) {}

    /**
     * 轮询结果。
     *
     * @param status       提供方侧任务状态
     * @param videoUrl     生成完成后的视频地址，未完成或失败时为 null
     * @param errorMessage 失败原因，成功或未完成时为 null
     * @param progress     进度百分比（0-100）
     */
    record PollResult(RemoteStatus status, String videoUrl, String errorMessage, int progress) {}

    /**
     * 连接自检结果。detail 为面向用户的说明文案，绝不包含任何密钥原文或片段；
     * status=OK 之外不得出现"成功"字样。
     */
    record ConnectivityResult(VideoProvider.ConnectivityStatus status, String detail) {}

    /**
     * 提交数字人视频生成任务。
     *
     * @param apiKey       通道管理卡片 key，可空（实现内按卡片→设置顺序解析，无 surrogate）
     * @param imageUrl     人物图 URL（需公网可访问）
     * @param audioUrlOrNull 音频 URL（可空；为空则用 script 文本驱动 TTS）
     * @param scriptOrNull 文案（可空；为空则必须提供 audioUrl）
     * @return 提交结果
     */
    SubmitResult submit(String apiKey, String imageUrl, String audioUrlOrNull, String scriptOrNull);

    /**
     * 轮询任务状态。
     *
     * @param apiKey 通道管理卡片 key，可空
     * @param talkId 提供方 talk ID
     * @return 轮询结果
     */
    PollResult poll(String apiKey, String talkId);

    /**
     * 连接自检（零费用）。默认为不支持，各提供方按需重写。
     */
    default ConnectivityResult probe(String apiKey) {
        return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNSUPPORTED, "该提供方暂不支持连接自检");
    }

    /** 返回提供方名称，例如 "did-avatar"。 */
    String name();
}
