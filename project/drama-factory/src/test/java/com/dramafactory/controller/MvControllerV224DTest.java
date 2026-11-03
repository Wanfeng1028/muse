package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MvSong;
import com.dramafactory.service.MvService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * MvController 分支覆盖补充测试（直接 new 控制器，不使用 MockMvc）。
 *
 * 覆盖：
 *  - compose 第 111 行 body == null 的 false 臂（连带 126 / 127 行 null 臂）
 *  - video 第 227 行 !Files.exists(target) / !Files.isRegularFile(target) / else 三个臂
 *  - safe 第 237 行 m == null 与 m.length() > 300 两个臂
 *
 * 诚实跳过清单（源码级理由，见文件末尾注释）。
 */
class MvControllerV224DTest {

    private MvService mvService;

    @BeforeEach
    void setUp() {
        mvService = mock(MvService.class);
    }

    // ------------------------------------------------------------------
    // compose: 第 111 行 if (body != null) 的 false 臂
    //          第 126 行 song.getAudioUrl() == null 的 true 臂
    //          第 127 行 song.getDurationMs() == null 的 true 臂
    // ------------------------------------------------------------------
    @Test
    void compose_bodyNull_mapsNullAudioUrlToEmptyStringAndNullDurationToZero() {
        MvSong song = new MvSong();
        song.setAudioUrl(null);
        song.setDurationMs(null);

        lenient().when(mvService.compose(eq(1L), isNull(), isNull())).thenReturn(song);

        MvController controller = new MvController(mvService, tempDir.toString());
        ResponseEntity<Map<String, Object>> response = controller.compose(1L, null);

        assertEquals(200, response.getStatusCode().value());
        Map<String, Object> body = response.getBody();
        assertNotNull(body);
        assertEquals("SUCCEEDED", body.get("status"));
        assertEquals("", body.get("audioUrl"));
        assertEquals(0, body.get("durationMs"));
    }

    // ------------------------------------------------------------------
    // video: 第 227 行 !Files.exists(target) == true 臂
    // ------------------------------------------------------------------
    @Test
    void video_targetDoesNotExist_throwsResourceNotFoundException() {
        MvController controller = new MvController(mvService, tempDir.toString());

        assertThrows(ResourceNotFoundException.class, () -> controller.video(7L));
    }

    // ------------------------------------------------------------------
    // video: 第 227 行 !Files.isRegularFile(target) == true 臂
    //        （target 存在但是目录）
    // ------------------------------------------------------------------
    @Test
    void video_targetExistsButIsDirectory_throwsResourceNotFoundException() throws Exception {
        Path mvDir = tempDir.resolve("mv").resolve("7");
        Files.createDirectories(mvDir);
        Path target = mvDir.resolve("final.mp4");
        Files.createDirectories(target);

        MvController controller = new MvController(mvService, tempDir.toString());

        assertThrows(ResourceNotFoundException.class, () -> controller.video(7L));
    }

    // ------------------------------------------------------------------
    // video: 第 227 行 else 臂（存在且为普通文件，正常返回）
    // ------------------------------------------------------------------
    @Test
    void video_targetIsRegularFile_returnsOkWithVideoMp4ContentType() throws Exception {
        Path mvDir = tempDir.resolve("mv").resolve("7");
        Files.createDirectories(mvDir);
        Path target = mvDir.resolve("final.mp4");
        Files.write(target, "fake-mp4-bytes".getBytes(StandardCharsets.UTF_8));

        MvController controller = new MvController(mvService, tempDir.toString());
        ResponseEntity<Resource> response = controller.video(7L);

        assertEquals(200, response.getStatusCode().value());
        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertEquals(MediaType.parseMediaType("video/mp4"), contentType);
        assertNotNull(response.getBody());
    }

    // ------------------------------------------------------------------
    // safe: 第 237 行 m == null 臂（IllegalStateException 无参构造，getMessage() == null）
    // ------------------------------------------------------------------
    @Test
    void compose_serviceThrowsIllegalStateWithoutMessage_safeReturnsOperationFailed() {
        lenient().when(mvService.compose(eq(2L), isNull(), isNull()))
                .thenThrow(new IllegalStateException());

        MvController controller = new MvController(mvService, tempDir.toString());
        ResponseEntity<Map<String, Object>> response = controller.compose(2L, Map.of());

        assertEquals(400, response.getStatusCode().value());
        Map<String, Object> body = response.getBody();
        assertNotNull(body);
        assertEquals("FAILED", body.get("status"));
        assertEquals("操作失败", body.get("error"));
    }

    // ------------------------------------------------------------------
    // safe: 第 237 行 m.length() > 300 臂（消息长度 400，应被截断到 300）
    // ------------------------------------------------------------------
    @Test
    void compose_serviceThrowsIllegalStateWithLongMessage_safeTruncatesTo300Chars() {
        String longMessage = "e".repeat(400);
        lenient().when(mvService.compose(eq(2L), isNull(), isNull()))
                .thenThrow(new IllegalStateException(longMessage));

        MvController controller = new MvController(mvService, tempDir.toString());
        ResponseEntity<Map<String, Object>> response = controller.compose(2L, Map.of());

        assertEquals(400, response.getStatusCode().value());
        Map<String, Object> body = response.getBody();
        assertNotNull(body);
        assertEquals("FAILED", body.get("status"));
        Object error = body.get("error");
        assertNotNull(error);
        assertEquals(300, error.toString().length());
        assertEquals("e".repeat(300), error.toString());
    }

    @TempDir
    Path tempDir;
}

/*
 * 诚实跳过清单
 *
 * 1. 第 219 行 `if (!sid.matches("^[A-Za-z0-9._-]{1,128}$"))` 的 true 臂：
 *    方法签名 `video(@PathVariable Long id)`，`sid = String.valueOf(id)`。
 *    Long 型 id 的字符串形式恒为可选负号 + 纯数字，恒满足 `^[A-Za-z0-9._-]{1,128}$`
 *    （长度上限 128 亦不会超），直接调用无法构造不匹配的入参。分支不可达，不写测试。
 *
 * 2. 第 224 行 `if (!target.startsWith(baseDir))` 的 true 臂：
 *    `baseDir = Paths.get(storageDir, "mv").normalize()`，
 *    `target = baseDir.resolve(sid).resolve("final.mp4").normalize()`。
 *    sid 恒为纯数字（见上），resolve 的子路径不会逃出 baseDir，
 *    normalize 后恒以 baseDir 为前缀，分支不可达，不写测试。
 */
