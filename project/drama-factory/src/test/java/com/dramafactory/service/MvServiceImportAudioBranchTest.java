package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.multipart.MultipartFile;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest
class MvServiceImportAudioBranchTest {

    @Autowired
    private MvService mvService;

    @MockBean
    private MvLyricsService mvLyricsService;

    @MockBean
    private com.dramafactory.service.byok.ByokGenerateService byokGenerateService;

    @Test
    void importAudio_nullTitle_throws() {
        MultipartFile file = new MockMultipartFile("f", "a.mp3", "audio/mpeg", new byte[]{1});
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, null, "lyrics", "mood", "style"));
        assertTrue(ex.getMessage().contains("标题不能为空"), "实际消息: " + ex.getMessage());
    }

    @Test
    void importAudio_blankTitle_throws() {
        MultipartFile file = new MockMultipartFile("f", "a.mp3", "audio/mpeg", new byte[]{1});
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, " ", "lyrics", "mood", "style"));
        assertTrue(ex.getMessage().contains("标题不能为空"), "实际消息: " + ex.getMessage());
    }

    @Test
    void importAudio_nullFile_throws() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(null, "标题", "lyrics", "mood", "style"));
        assertTrue(ex.getMessage().contains("上传文件不能为空"), "实际消息: " + ex.getMessage());
    }

    @Test
    void importAudio_emptyFile_throws() {
        MultipartFile file = new MockMultipartFile("f", "a.mp3", "audio/mpeg", new byte[0]);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, "标题", "lyrics", "mood", "style"));
        assertTrue(ex.getMessage().contains("上传文件不能为空"), "实际消息: " + ex.getMessage());
    }

    @Test
    void importAudio_oversize_throws() {
        MultipartFile f = mock(MultipartFile.class);
        when(f.isEmpty()).thenReturn(false);
        when(f.getSize()).thenReturn(101L * 1024 * 1024);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(f, "标题", "lyrics", "mood", "style"));
        assertTrue(ex.getMessage().contains("超过大小限制"), "实际消息: " + ex.getMessage());
    }

    @Test
    void importAudio_badExt_throws() {
        MultipartFile file = new MockMultipartFile("f", "a.txt", "audio/mpeg", new byte[]{1});
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, "标题", "lyrics", "mood", "style"));
        assertTrue(ex.getMessage().contains("仅支持 mp3 / wav / m4a"), "实际消息: " + ex.getMessage());
    }

    @Test
    void importAudio_nullFilename_throws() {
        MultipartFile file = new MockMultipartFile("f", null, "audio/mpeg", new byte[]{1});
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, "标题", "lyrics", "mood", "style"));
        assertTrue(ex.getMessage().contains("仅支持 mp3 / wav / m4a"), "实际消息: " + ex.getMessage());
    }

    @Test
    void importAudio_badMime_throws() {
        MultipartFile file = new MockMultipartFile("f", "a.mp3", "video/mp4", new byte[]{1});
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> mvService.importAudio(file, "标题", "lyrics", "mood", "style"));
        assertTrue(ex.getMessage().contains("不支持的音频类型"), "实际消息: " + ex.getMessage());
    }
}
