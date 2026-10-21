package com.dramafactory.media;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

import java.util.List;

class MediaProfileServiceDeepTest {

    private final MediaProfileService service = new MediaProfileService();

    @Test
    void list_returnsImmutable() {
        Assertions.assertThrows(UnsupportedOperationException.class, () -> service.list().add(null));
    }

    @Test
    void list_nineUniqueNames() {
        List<MediaProfile> profiles = service.list();
        Assertions.assertEquals(9, profiles.size());
        List<String> names = profiles.stream().map(MediaProfile::name).toList();
        // 互不相同
        Assertions.assertEquals(9, names.stream().distinct().count());
        // 包含指定名称
        Assertions.assertTrue(names.contains("youtube_landscape"));
        Assertions.assertTrue(names.contains("youtube_4k"));
        Assertions.assertTrue(names.contains("youtube_shorts"));
        Assertions.assertTrue(names.contains("instagram_reels"));
        Assertions.assertTrue(names.contains("instagram_feed"));
        Assertions.assertTrue(names.contains("tiktok"));
        Assertions.assertTrue(names.contains("linkedin"));
        Assertions.assertTrue(names.contains("cinematic"));
        Assertions.assertTrue(names.contains("generic_hd"));
    }

    @Test
    void forPlatform_instagram_returnsTwoInOrder() {
        List<MediaProfile> result = service.forPlatform("instagram");
        List<String> names = result.stream().map(MediaProfile::name).toList();
        Assertions.assertEquals(List.of("instagram_reels", "instagram_feed"), names);
    }

    @Test
    void forPlatform_youtube_returnsThreeInOrder() {
        List<MediaProfile> result = service.forPlatform("youtube");
        List<String> names = result.stream().map(MediaProfile::name).toList();
        Assertions.assertEquals(List.of("youtube_landscape", "youtube_4k", "youtube_shorts"), names);
    }

    @Test
    void forPlatform_unknown_returnsEmpty() {
        List<MediaProfile> result = service.forPlatform("bilibili");
        Assertions.assertTrue(result.isEmpty());
    }

    @Test
    void forPlatform_emptyPrefix_returnsAll() {
        List<MediaProfile> result = service.forPlatform("");
        List<MediaProfile> all = service.list();
        Assertions.assertEquals(all.size(), result.size());
        for (int i = 0; i < all.size(); i++) {
            Assertions.assertEquals(all.get(i).name(), result.get(i).name());
        }
    }

    @Test
    void get_youtube4k_values() {
        MediaProfile p = service.get("youtube_4k");
        Assertions.assertEquals(3840, p.width());
        Assertions.assertEquals(2160, p.height());
        Assertions.assertEquals("16:9", p.aspectRatio());
        Assertions.assertEquals(30, p.fps());
        Assertions.assertEquals(18, p.crf());
    }

    @Test
    void get_unknown_messageListsAvailable() {
        IllegalArgumentException ex = Assertions.assertThrows(IllegalArgumentException.class, () -> service.get("nope"));
        String msg = ex.getMessage();
        Assertions.assertTrue(msg.contains("nope"));
        Assertions.assertTrue(msg.contains("Available:"));
        Assertions.assertTrue(msg.contains("tiktok"));
    }

    @Test
    void ffmpegArgs_tiktok_exactSequence() {
        MediaProfile p = service.get("tiktok");
        List<String> args = service.ffmpegOutputArgs(p);
        Assertions.assertEquals(List.of("-c:v", "libx264", "-c:a", "aac", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", "-vf", "scale=1080:1920"), args);
    }

    @Test
    void ffmpegArgs_cinematic_values() {
        MediaProfile p = service.get("cinematic");
        List<String> args = service.ffmpegOutputArgs(p);
        int crfIndex = args.indexOf("-crf");
        Assertions.assertEquals("16", args.get(crfIndex + 1));
        int rIndex = args.indexOf("-r");
        Assertions.assertEquals("24", args.get(rIndex + 1));
        int vfIndex = args.indexOf("-vf");
        Assertions.assertEquals("scale=2560:1080", args.get(vfIndex + 1));
    }

    @Test
    void orientationConsistency() {
        MediaProfile shorts = service.get("youtube_shorts");
        Assertions.assertTrue(shorts.height() > shorts.width());
        Assertions.assertEquals("9:16", shorts.aspectRatio());

        MediaProfile reels = service.get("instagram_reels");
        Assertions.assertTrue(reels.height() > reels.width());
        Assertions.assertEquals("9:16", reels.aspectRatio());

        MediaProfile tiktok = service.get("tiktok");
        Assertions.assertTrue(tiktok.height() > tiktok.width());
        Assertions.assertEquals("9:16", tiktok.aspectRatio());

        MediaProfile feed = service.get("instagram_feed");
        Assertions.assertEquals(feed.width(), feed.height());
        Assertions.assertEquals("1:1", feed.aspectRatio());

        MediaProfile landscape = service.get("youtube_landscape");
        Assertions.assertTrue(landscape.width() > landscape.height());
        Assertions.assertEquals("16:9", landscape.aspectRatio());
    }

    @Test
    void durationAndSizeLimits() {
        MediaProfile shorts = service.get("youtube_shorts");
        Assertions.assertEquals(60.0, shorts.maxDurationSeconds());

        MediaProfile tiktok = service.get("tiktok");
        Assertions.assertEquals(600.0, tiktok.maxDurationSeconds());

        MediaProfile landscape = service.get("youtube_landscape");
        Assertions.assertNull(landscape.maxDurationSeconds());

        MediaProfile reels = service.get("instagram_reels");
        Assertions.assertEquals(250.0, reels.maxFileSizeMb());
    }
}