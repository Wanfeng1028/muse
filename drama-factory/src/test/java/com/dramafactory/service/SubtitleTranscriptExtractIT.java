package com.dramafactory.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class SubtitleTranscriptExtractIT {

    private static Path withSubVideo;
    private static Path noSubVideo;

    @TempDir
    Path tempDir;

    @BeforeAll
    static void generateTestVideos() throws Exception {
        Path videoDir = Path.of("target/test-transcript");
        Files.createDirectories(videoDir);

        // 生成 subs.srt 字幕文件
        String srtContent = "1\n" +
                "00:00:00,000 --> 00:00:02,000\n" +
                "你好，这是第一镜\n" +
                "\n" +
                "2\n" +
                "00:00:02,000 --> 00:00:04,000\n" +
                "第二镜的字幕内容\n" +
                "\n" +
                "3\n" +
                "00:00:04,000 --> 00:00:06,000\n" +
                "第三镜结束\n";
        Path srtPath = videoDir.resolve("subs.srt");
        Files.writeString(srtPath, srtContent);

        // 生成带内嵌字幕的视频 with-sub.mp4
        withSubVideo = videoDir.resolve("with-sub.mp4");
        ProcessBuilder pbWithSub = new ProcessBuilder(
                "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=10",
                "-i", srtPath.toString(),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:s", "mov_text", "-shortest", withSubVideo.toString()
        );
        pbWithSub.inheritIO();
        Process procWithSub = pbWithSub.start();
        assertTrue(procWithSub.waitFor(120, TimeUnit.SECONDS), "生成带字幕视频超时");
        int exitWithSub = procWithSub.exitValue();
        assertEquals(0, exitWithSub, "生成带字幕视频失败");

        // 生成无字幕视频 no-sub.mp4
        noSubVideo = videoDir.resolve("no-sub.mp4");
        ProcessBuilder pbNoSub = new ProcessBuilder(
                "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", noSubVideo.toString()
        );
        pbNoSub.inheritIO();
        Process procNoSub = pbNoSub.start();
        assertTrue(procNoSub.waitFor(120, TimeUnit.SECONDS), "生成无字幕视频超时");
        int exitNoSub = procNoSub.exitValue();
        assertEquals(0, exitNoSub, "生成无字幕视频失败");
    }

    @Test
    void extract_带内嵌字幕() throws Exception {
        SubtitleTranscriptService service = new SubtitleTranscriptService(
                new FfmpegService("ffmpeg", "ffprobe"), new ObjectMapper()
        );

        SubtitleTranscriptService.TranscriptResult r = service.extract(withSubVideo, tempDir);

        assertTrue(r.found());
        assertEquals(3, r.segments().size());

        SubtitleTranscriptService.TranscriptSegment first = r.segments().get(0);
        assertEquals(0.0, first.startSec(), 0.2);
        assertEquals(2.0, first.endSec(), 0.2);
        assertEquals("你好，这是第一镜", first.text());

        assertTrue(r.trackInfo().contains("s:"));
    }

    @Test
    void extract_无字幕视频() throws Exception {
        SubtitleTranscriptService service = new SubtitleTranscriptService(
                new FfmpegService("ffmpeg", "ffprobe"), new ObjectMapper()
        );

        SubtitleTranscriptService.TranscriptResult r = service.extract(noSubVideo, tempDir);

        assertFalse(r.found());
        assertTrue(r.segments().isEmpty());
    }
}