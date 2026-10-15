package com.dramafactory.service;

/*
 * 诚实跳过清单（依据 jacoco missed-branch 清单，逐条给理由，不写测试）：
 * 1. L453 render 内 clips.isEmpty()：空 sections 的 Timeline 无法经 fromJson/align/buildInstrumentalTimeline
 *    构造出来，public 路径不可达。
 * 2. L468 render 内字幕过滤分支：需走完真实 ffmpeg 渲染链路（generateTestClip/concatClips/muxAudio），
 *    mock 下断言脆弱，不测。
 * 3. L541 findStep 的 getSeqNo()==null 臂：AgentStep.SEQ_NO 列 NOT NULL，null 存不进 DB，mock 硬造无业务意义。
 * 4. L570 resolveLocalAudio 的 filePath==null 臂：Asset.FILE_PATH 列 NOT NULL，同理（filePath 含 ".." 的半支已有测试覆盖）。
 */

import com.dramafactory.model.MvSong;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.MvSongRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.service.byok.ByokGenerateService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class MvServiceV223DTest {

    private MvService newService(FfmpegService ffmpegService) {
        MvSongRepository mvSongRepository = mock(MvSongRepository.class);
        RunRepository runRepository = mock(RunRepository.class);
        AgentStepRepository agentStepRepository = mock(AgentStepRepository.class);
        MvLyricsService mvLyricsService = mock(MvLyricsService.class);
        ByokGenerateService byokGenerateService = mock(ByokGenerateService.class);
        MvTimelineService mvTimelineService = mock(MvTimelineService.class);
        AssetService assetService = mock(AssetService.class);
        AssetRepository assetRepository = mock(AssetRepository.class);
        return new MvService(mvSongRepository, runRepository, agentStepRepository, mvLyricsService,
                byokGenerateService, ffmpegService, mvTimelineService, new ObjectMapper(),
                assetService, assetRepository);
    }

    // ---- L142: originalName == null 臂 ----
    @Test
    void importAudio_withNullOriginalFilename_throwsUnsupportedExtension() {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        MvService mvService = newService(ffmpegService);

        MultipartFile file = new MultipartFile() {
            @Override
            public String getName() {
                return "file";
            }

            @Override
            public String getOriginalFilename() {
                return null;
            }

            @Override
            public String getContentType() {
                return "audio/mpeg";
            }

            @Override
            public boolean isEmpty() {
                return false;
            }

            @Override
            public long getSize() {
                return 1L;
            }

            @Override
            public byte[] getBytes() {
                return new byte[]{0};
            }

            @Override
            public InputStream getInputStream() {
                return InputStream.nullInputStream();
            }

            @Override
            public void transferTo(File dest) {
                // no-op
            }
        };

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, "t", null, "m", "s"));
        assertTrue(ex.getMessage().contains("仅支持 mp3 / wav / m4a"));
    }

    // ---- L149: mime 为空串臂 ----
    @Test
    void importAudio_withBlankMime_skipsMimeCheck() {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        MvService mvService = newService(ffmpegService);

        MockMultipartFile file = new MockMultipartFile("f", "a.mp3", "", new byte[]{1});
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> mvService.importAudio(file, "t", null, "m", "s"));
        assertFalse(ex.getMessage() != null && ex.getMessage().contains("不支持的音频类型"));
    }

    // ---- L149: mime == "application/octet-stream" 臂 ----
    @Test
    void importAudio_withOctetStreamMime_skipsMimeCheck() {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        MvService mvService = newService(ffmpegService);

        MockMultipartFile file = new MockMultipartFile("f", "a.mp3", "application/octet-stream", new byte[]{1});
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> mvService.importAudio(file, "t", null, "m", "s"));
        assertFalse(ex.getMessage() != null && ex.getMessage().contains("不支持的音频类型"));
    }

    // ---- L152: 各 mime 变体臂 ----
    @Test
    void importAudio_withWavMime_accepted() {
        assertAcceptedMime("audio/wav");
    }

    @Test
    void importAudio_withXWavMime_accepted() {
        assertAcceptedMime("audio/x-wav");
    }

    @Test
    void importAudio_withMp4Mime_accepted() {
        assertAcceptedMime("audio/mp4");
    }

    @Test
    void importAudio_withXM4aMime_accepted() {
        assertAcceptedMime("audio/x-m4a");
    }

    @Test
    void importAudio_withAacMime_accepted() {
        assertAcceptedMime("audio/aac");
    }

    @Test
    void importAudio_withTextPlainMime_throwsUnsupportedType() {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        MvService mvService = newService(ffmpegService);

        MockMultipartFile file = new MockMultipartFile("f", "a.mp3", "text/plain", new byte[]{1});
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, "t", null, "m", "s"));
        assertTrue(ex.getMessage().contains("不支持的音频类型"));
    }

    private void assertAcceptedMime(String mime) {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        MvService mvService = newService(ffmpegService);
        MockMultipartFile file = new MockMultipartFile("f", "a.mp3", mime, new byte[]{1});
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> mvService.importAudio(file, "t", null, "m", "s"));
        assertFalse(ex.getMessage() != null && ex.getMessage().contains("不支持的音频类型"));
    }

    // ---- L255: cur 为空臂（文本以空行结尾） ----
    @Test
    void buildLyricsJsonFromText_trailingBlankLine_ok() {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        MvService mvService = newService(ffmpegService);

        String json = mvService.buildLyricsJsonFromText("t", "第一句\n\n第二句\n\n");
        assertNotNull(json);
        assertTrue(json.contains("sections"));
    }

    @Test
    void buildLyricsJsonFromText_noTrailingBlankLine_ok() {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        MvService mvService = newService(ffmpegService);

        String json = mvService.buildLyricsJsonFromText("t", "第一句\n\n第二句");
        assertNotNull(json);
        assertTrue(json.contains("sections"));
    }

    // ---- L587: writeSrt 中 text == null 臂 ----
    @Test
    void writeSrt_withNullText_writesEmptyLine(@TempDir Path tempDir) throws Exception {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        MvService mvService = newService(ffmpegService);

        Class<?> st = Class.forName("com.dramafactory.service.MvService$SectionTiming");
        Constructor<?> c = st.getDeclaredConstructor(long.class, long.class, String.class);
        c.setAccessible(true);
        Object timing = c.newInstance(0L, 1000L, null);

        Path out = tempDir.resolve("t.srt");
        Method m = MvService.class.getDeclaredMethod("writeSrt", List.class, Path.class);
        m.setAccessible(true);
        m.invoke(mvService, List.of(timing), out);

        assertTrue(Files.exists(out));
        String content = Files.readString(out);
        assertTrue(content.contains("\r\n\r\n"));
    }

    // ---- L608: ffmpeg == null 臂 ----
    @Test
    void muxAudio_withNullFfmpeg_fallsBackAndFails(@TempDir Path tempDir) throws Exception {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        when(ffmpegService.getFfmpeg()).thenReturn(null);
        MvService mvService = newService(ffmpegService);

        Path video = tempDir.resolve("v.mp4");
        Path audio = tempDir.resolve("a.mp4");
        Path out = tempDir.resolve("o.mp4");

        Method m = MvService.class.getDeclaredMethod("muxAudio", Path.class, Path.class, Path.class);
        m.setAccessible(true);
        InvocationTargetException ex = assertThrows(InvocationTargetException.class,
                () -> m.invoke(mvService, video, audio, out));
        assertTrue(ex.getCause() instanceof RuntimeException);
        assertTrue(ex.getCause().getMessage().contains("音频合成失败"));
    }

    // ---- L608: ffmpeg.isBlank() 臂 ----
    @Test
    void muxAudio_withBlankFfmpeg_fallsBackAndFails(@TempDir Path tempDir) throws Exception {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        when(ffmpegService.getFfmpeg()).thenReturn(" ");
        MvService mvService = newService(ffmpegService);

        Path video = tempDir.resolve("v.mp4");
        Path audio = tempDir.resolve("a.mp4");
        Path out = tempDir.resolve("o.mp4");

        Method m = MvService.class.getDeclaredMethod("muxAudio", Path.class, Path.class, Path.class);
        m.setAccessible(true);
        InvocationTargetException ex = assertThrows(InvocationTargetException.class,
                () -> m.invoke(mvService, video, audio, out));
        assertTrue(ex.getCause() instanceof RuntimeException);
        assertTrue(ex.getCause().getMessage().contains("音频合成失败"));
    }

    // ---- L630: code != 0 臂 ----
    @Test
    void muxAudio_withNonZeroExit_throwsRuntimeException(@TempDir Path tempDir) throws Exception {
        FfmpegService ffmpegService = mock(FfmpegService.class);
        when(ffmpegService.getFfmpeg()).thenReturn("false");
        MvService mvService = newService(ffmpegService);

        Path video = tempDir.resolve("v.mp4");
        Path audio = tempDir.resolve("a.mp4");
        Path out = tempDir.resolve("o.mp4");

        Method m = MvService.class.getDeclaredMethod("muxAudio", Path.class, Path.class, Path.class);
        m.setAccessible(true);
        InvocationTargetException ex = assertThrows(InvocationTargetException.class,
                () -> m.invoke(mvService, video, audio, out));
        assertTrue(ex.getCause() instanceof RuntimeException);
        assertTrue(ex.getCause().getMessage().contains("音频合成失败"));
    }
}
