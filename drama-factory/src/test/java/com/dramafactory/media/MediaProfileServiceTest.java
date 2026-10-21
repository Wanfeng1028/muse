package com.dramafactory.media;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * 媒体预设服务的单元测试。
 */
class MediaProfileServiceTest {

    private final MediaProfileService service = new MediaProfileService();

    @Test
    void list_returnsNineProfilesInOrder() {
        List<MediaProfile> profiles = service.list();
        assertThat(profiles).hasSize(9);
        assertThat(profiles.get(0).name()).isEqualTo("youtube_landscape");
    }

    @Test
    void get_tiktok_returnsCorrectValues() {
        MediaProfile tiktok = service.get("tiktok");
        assertThat(tiktok.width()).isEqualTo(1080);
        assertThat(tiktok.height()).isEqualTo(1920);
        assertThat(tiktok.aspectRatio()).isEqualTo("9:16");
        assertThat(tiktok.maxFileSizeMb()).isEqualTo(287.0);
        assertThat(tiktok.maxDurationSeconds()).isEqualTo(600.0);
    }

    @Test
    void get_cinematic_returnsCorrectValues() {
        MediaProfile cinematic = service.get("cinematic");
        assertThat(cinematic.width()).isEqualTo(2560);
        assertThat(cinematic.height()).isEqualTo(1080);
        assertThat(cinematic.fps()).isEqualTo(24);
        assertThat(cinematic.crf()).isEqualTo(16);
        assertThat(cinematic.maxFileSizeMb()).isNull();
    }

    @Test
    void get_instagramFeed_hasDefaultCaptionFormat() {
        MediaProfile feed = service.get("instagram_feed");
        assertThat(feed.captionFormat()).isEqualTo("srt");
    }

    @Test
    void forPlatform_youtube_returnsThreeInOrder() {
        List<MediaProfile> youtube = service.forPlatform("youtube");
        assertThat(youtube).hasSize(3);
        assertThat(youtube.get(0).name()).isEqualTo("youtube_landscape");
        assertThat(youtube.get(1).name()).isEqualTo("youtube_4k");
        assertThat(youtube.get(2).name()).isEqualTo("youtube_shorts");
    }

    @Test
    void get_unknownName_throwsWithMessage() {
        assertThatThrownBy(() -> service.get("unknown"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Unknown profile")
                .hasMessageContaining("tiktok");
    }

    @Test
    void ffmpegOutputArgs_youtubeShorts_matchesExpected() {
        MediaProfile shorts = service.get("youtube_shorts");
        List<String> args = service.ffmpegOutputArgs(shorts);
        assertThat(args).containsExactly(
                "-c:v", "libx264",
                "-c:a", "aac",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                "-vf", "scale=1080:1920"
        );
    }
}
