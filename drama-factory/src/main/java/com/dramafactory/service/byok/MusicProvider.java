package com.dramafactory.service.byok;

import com.dramafactory.service.video.VideoProvider;

/**
 * 音乐生成提供方抽象接口（BYOK，同步）。
 */
public interface MusicProvider {

    /** 生成结果：音频地址（24 小时有效，调用方需下载落盘）与时长毫秒数（可空）。 */
    record GenerateResult(String audioUrl, Integer durationMs) {}

    /**
     * 连接自检结果。detail 为面向用户的说明文案，绝不包含任何密钥原文或片段；
     * status=OK 之外不得出现"成功"字样。
     */
    record ConnectivityResult(VideoProvider.ConnectivityStatus status, String detail) {}

    /**
     * 生成音乐（同步）。
     *
     * @param apiKey      通道管理卡片 key，可空（实现内按卡片→设置顺序解析，无 surrogate）
     * @param apiBase     API 基地址，可空（实现内用默认值）
     * @param modelId     模型 ID（取用户在通道管理配置的模型）
     * @param prompt      风格描述
     * @param lyrics      歌词；纯音乐模式可空
     * @param instrumental 是否纯音乐（无歌词）
     * @return 生成结果
     */
    GenerateResult generate(String apiKey, String apiBase, String modelId, String prompt, String lyrics, boolean instrumental);

    /**
     * 连接自检（零费用）。默认为不支持，各提供方按需重写。
     */
    default ConnectivityResult probe(String apiKey, String apiBase) {
        return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNSUPPORTED, "该提供方暂不支持连接自检");
    }

    /** 返回提供方名称，例如 "minimax-music"。 */
    String name();
}
