package com.dramafactory.media;

import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 媒体预设注册表服务，提供平台媒体预设的查询与 FFmpeg 参数生成能力。
 */
@Service
public class MediaProfileService {

    private static final List<MediaProfile> PROFILES = List.of(
            new MediaProfile(
                    "youtube_landscape",
                    1920, 1080,
                    "16:9",
                    30,
                    "libx264", "aac", 18,
                    "yuv420p",
                    null, null,
                    "srt",
                    "YouTube standard HD upload"
            ),
            new MediaProfile(
                    "youtube_4k",
                    3840, 2160,
                    "16:9",
                    30,
                    "libx264", "aac", 18,
                    "yuv420p",
                    null, null,
                    "srt",
                    "YouTube 4K upload"
            ),
            new MediaProfile(
                    "youtube_shorts",
                    1080, 1920,
                    "9:16",
                    30,
                    "libx264", "aac", 20,
                    "yuv420p",
                    null, 60.0,
                    "srt",
                    "YouTube Shorts (max 60s, vertical)"
            ),
            new MediaProfile(
                    "instagram_reels",
                    1080, 1920,
                    "9:16",
                    30,
                    "libx264", "aac", 20,
                    "yuv420p",
                    250.0, 90.0,
                    "srt",
                    "Instagram Reels (max 90s, vertical)"
            ),
            new MediaProfile(
                    "instagram_feed",
                    1080, 1080,
                    "1:1",
                    30,
                    "libx264", "aac", 20,
                    "yuv420p",
                    250.0, 60.0,
                    "srt",
                    "Instagram feed video (square)"
            ),
            new MediaProfile(
                    "tiktok",
                    1080, 1920,
                    "9:16",
                    30,
                    "libx264", "aac", 20,
                    "yuv420p",
                    287.0, 600.0,
                    "srt",
                    "TikTok (max 10min, vertical preferred)"
            ),
            new MediaProfile(
                    "linkedin",
                    1920, 1080,
                    "16:9",
                    30,
                    "libx264", "aac", 20,
                    "yuv420p",
                    5120.0, 600.0,
                    "srt",
                    "LinkedIn video (landscape preferred, max 10min)"
            ),
            new MediaProfile(
                    "cinematic",
                    2560, 1080,
                    "21:9",
                    24,
                    "libx264", "aac", 16,
                    "yuv420p",
                    null, null,
                    "srt",
                    "Cinematic ultra-wide format"
            ),
            new MediaProfile(
                    "generic_hd",
                    1920, 1080,
                    "16:9",
                    30,
                    "libx264", "aac", 23,
                    "yuv420p",
                    null, null,
                    "srt",
                    "Generic HD output (no platform-specific constraints)"
            )
    );

    /**
     * 获取全部媒体预设，按注册顺序返回不可变列表。
     *
     * @return 不可变的媒体预设列表
     */
    public List<MediaProfile> list() {
        return PROFILES;
    }

    /**
     * 按名称获取媒体预设。
     *
     * @param name 预设名称
     * @return 对应的媒体预设
     * @throws IllegalArgumentException 当名称不存在时抛出
     */
    public MediaProfile get(String name) {
        for (MediaProfile p : PROFILES) {
            if (p.name().equals(name)) {
                return p;
            }
        }
        String available = PROFILES.stream()
                .map(MediaProfile::name)
                .collect(Collectors.joining(", "));
        throw new IllegalArgumentException(
                "Unknown profile '" + name + "'. Available: " + available
        );
    }

    /**
     * 获取指定平台前缀的所有媒体预设，保持注册顺序。
     *
     * @param platform 平台前缀
     * @return 匹配的媒体预设列表
     */
    public List<MediaProfile> forPlatform(String platform) {
        List<MediaProfile> result = new ArrayList<>();
        for (MediaProfile p : PROFILES) {
            if (p.name().startsWith(platform)) {
                result.add(p);
            }
        }
        return result;
    }

    /**
     * 生成 FFmpeg 输出参数。
     *
     * @param p 媒体预设
     * @return FFmpeg 输出参数列表
     */
    public List<String> ffmpegOutputArgs(MediaProfile p) {
        return List.of(
                "-c:v", p.codec(),
                "-c:a", p.audioCodec(),
                "-crf", String.valueOf(p.crf()),
                "-pix_fmt", p.pixelFormat(),
                "-r", String.valueOf(p.fps()),
                "-vf", "scale=" + p.width() + ":" + p.height()
        );
    }
}
