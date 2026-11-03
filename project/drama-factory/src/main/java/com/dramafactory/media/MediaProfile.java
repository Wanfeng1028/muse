package com.dramafactory.media;

/**
 * 媒体渲染预设记录，对应目标平台/格式的命名渲染配置。
 *
 * @param name              预设名称
 * @param width             视频宽度（像素）
 * @param height            视频高度（像素）
 * @param aspectRatio       宽高比（如 "16:9"、"9:16"、"1:1"、"21:9"）
 * @param fps               帧率
 * @param codec             视频编码器
 * @param audioCodec        音频编码器
 * @param crf               恒定质量因子
 * @param pixelFormat       像素格式
 * @param maxFileSizeMb     最大文件大小（MB），可为 null
 * @param maxDurationSeconds 最大时长（秒），可为 null
 * @param captionFormat     字幕格式
 * @param notes             备注说明
 */
public record MediaProfile(
        String name,
        int width,
        int height,
        String aspectRatio,
        int fps,
        String codec,
        String audioCodec,
        int crf,
        String pixelFormat,
        Double maxFileSizeMb,
        Double maxDurationSeconds,
        String captionFormat,
        String notes
) {
}
