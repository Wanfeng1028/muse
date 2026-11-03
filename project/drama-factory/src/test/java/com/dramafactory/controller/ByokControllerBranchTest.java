package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.service.byok.ByokGenerateService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.when;

class ByokControllerBranchTest {

    private ByokGenerateService service;

    @TempDir
    Path tempDir;

    private ByokController controller;

    @BeforeEach
    void setUp() {
        service = mock(ByokGenerateService.class);
        reset(service);
        controller = new ByokController(service, tempDir.toString());
    }

    // 分支：generate/body为null -> 400 不支持的模块
    @Test
    void generateNullBodyIs400() {
        ResponseEntity<Map<String, String>> resp = controller.generate(null);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertEquals("不支持的模块：", resp.getBody().get("error"));
    }

    // 分支：generate/module为null -> 400 不支持的模块
    @Test
    void generateNullModuleIs400() {
        ByokController.GenerateBody body = new ByokController.GenerateBody(null, 1L, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertEquals("不支持的模块：null", resp.getBody().get("error"));
    }

    // 分支：generate/providerId为null -> 400 缺少必要参数
    @Test
    void generateNullProviderIdIs400() {
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", null, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("缺少必要参数", resp.getBody().get("error"));
    }

    // 分支：generate/modelId为null -> 400 缺少必要参数
    @Test
    void generateNullModelIdIs400() {
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, null, "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("缺少必要参数", resp.getBody().get("error"));
    }

    // 分支：generate/modelId为空白 -> 400 缺少必要参数
    @Test
    void generateBlankModelIdIs400() {
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, " ", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("缺少必要参数", resp.getBody().get("error"));
    }

    // 分支：generate/prompt为null -> 400 请填写提示词
    @Test
    void generateNullPromptIs400() {
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", null, null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("请填写提示词", resp.getBody().get("error"));
    }

    // 分支：generate/成功 -> 200 SUCCEEDED 且 url 为桩返回值
    @Test
    void generateSuccess() {
        when(service.generate(any(ByokGenerateService.GenerateRequest.class)))
                .thenReturn(new ByokGenerateService.GenerateResponse("SUCCEEDED", "/api/byok/file/image/x.png", null));
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertEquals("/api/byok/file/image/x.png", resp.getBody().get("url"));
    }

    // 分支：generate/成功但url为null -> url 转为空字符串
    @Test
    void generateNullUrlToEmptyString() {
        when(service.generate(any(ByokGenerateService.GenerateRequest.class)))
                .thenReturn(new ByokGenerateService.GenerateResponse("SUCCEEDED", null, null));
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("SUCCEEDED", resp.getBody().get("status"));
        assertEquals("", resp.getBody().get("url"));
    }

    // 分支：generate/service抛IllegalArgumentException -> 400 使用异常消息
    @Test
    void generateIllegalArgumentIs400() {
        when(service.generate(any(ByokGenerateService.GenerateRequest.class)))
                .thenThrow(new IllegalArgumentException("bad param"));
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertEquals("bad param", resp.getBody().get("error"));
    }

    // 分支：generate/safe msg==null -> 使用异常类简单名
    @Test
    void generateIAENullMessageUsesClassName() {
        when(service.generate(any(ByokGenerateService.GenerateRequest.class)))
                .thenThrow(new IllegalArgumentException((String) null));
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("IllegalArgumentException", resp.getBody().get("error"));
    }

    // 分支：generate/safe msg.isBlank -> 使用异常类简单名
    @Test
    void generateIAEBlankMessageUsesClassName() {
        when(service.generate(any(ByokGenerateService.GenerateRequest.class)))
                .thenThrow(new IllegalArgumentException(" "));
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("IllegalArgumentException", resp.getBody().get("error"));
    }

    // 分支：generate/safe msg超长 -> 截断为500
    @Test
    void generateIAELongMessageTruncated() {
        when(service.generate(any(ByokGenerateService.GenerateRequest.class)))
                .thenThrow(new IllegalArgumentException("x".repeat(600)));
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals(500, resp.getBody().get("error").length());
    }

    // 分支：generate/ResourceNotFoundException 被原样 rethrow
    @Test
    void generateResourceNotFoundRethrown() {
        when(service.generate(any(ByokGenerateService.GenerateRequest.class)))
                .thenThrow(new ResourceNotFoundException("provider", 1L));
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", "hi", null);
        assertThrows(ResourceNotFoundException.class, () -> controller.generate(body));
    }

    // 分支：generate/其他异常 -> 500 使用异常消息
    @Test
    void generateUnexpectedIs500() {
        when(service.generate(any(ByokGenerateService.GenerateRequest.class)))
                .thenThrow(new RuntimeException("boom"));
        ByokController.GenerateBody body = new ByokController.GenerateBody("IMAGE", 1L, "m", "hi", null);
        ResponseEntity<Map<String, String>> resp = controller.generate(body);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("FAILED", resp.getBody().get("status"));
        assertEquals("boom", resp.getBody().get("error"));
    }

    // 分支：file/module为null -> 400
    @Test
    void fileNullModuleIs400() {
        ResponseEntity<org.springframework.core.io.Resource> resp = controller.file(null, "x.png");
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
    }

    // 分支：file/filename为null -> 400
    @Test
    void fileNullFilenameIs400() {
        ResponseEntity<org.springframework.core.io.Resource> resp = controller.file("image", null);
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
    }

    // 分支：file/filename不符合FILENAME_PATTERN -> 400
    @Test
    void fileBadPatternIs400() {
        ResponseEntity<org.springframework.core.io.Resource> resp = controller.file("image", "a b.png");
        assertEquals(HttpStatus.BAD_REQUEST, resp.getStatusCode());
    }

    // 分支：file/存在png -> 200 且 contentType=IMAGE_PNG
    @Test
    void filePngContentType() throws Exception {
        Path dir = tempDir.resolve("byok/image");
        Files.createDirectories(dir);
        Files.write(dir.resolve("x.png"), new byte[]{1, 2, 3});
        ResponseEntity<org.springframework.core.io.Resource> resp = controller.file("image", "x.png");
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals(MediaType.IMAGE_PNG, resp.getHeaders().getContentType());
    }

    // 分支：file/存在jpg与jpeg -> 200 且 contentType=IMAGE_JPEG
    @Test
    void fileJpgAndJpegContentType() throws Exception {
        Path dir = tempDir.resolve("byok/image");
        Files.createDirectories(dir);
        Files.write(dir.resolve("x.jpg"), new byte[]{1, 2, 3});
        Files.write(dir.resolve("x.jpeg"), new byte[]{1, 2, 3});
        ResponseEntity<org.springframework.core.io.Resource> resp1 = controller.file("image", "x.jpg");
        assertEquals(HttpStatus.OK, resp1.getStatusCode());
        assertEquals(MediaType.IMAGE_JPEG, resp1.getHeaders().getContentType());
        ResponseEntity<org.springframework.core.io.Resource> resp2 = controller.file("image", "x.jpeg");
        assertEquals(HttpStatus.OK, resp2.getStatusCode());
        assertEquals(MediaType.IMAGE_JPEG, resp2.getHeaders().getContentType());
    }

    // 分支：file/mp3与mp4与默认 -> 200 且 contentType 分别为 audio/mpeg、video/mp4、APPLICATION_OCTET_STREAM
    @Test
    void fileMp3Mp4AndDefaultContentType() throws Exception {
        Path musicDir = tempDir.resolve("byok/music");
        Files.createDirectories(musicDir);
        Files.write(musicDir.resolve("x.mp3"), new byte[]{1, 2, 3});

        Path avatarDir = tempDir.resolve("byok/avatar");
        Files.createDirectories(avatarDir);
        Files.write(avatarDir.resolve("x.mp4"), new byte[]{1, 2, 3});

        Path imageDir = tempDir.resolve("byok/image");
        Files.createDirectories(imageDir);
        Files.write(imageDir.resolve("x.txt"), new byte[]{1, 2, 3});

        ResponseEntity<org.springframework.core.io.Resource> respMp3 = controller.file("music", "x.mp3");
        assertEquals(HttpStatus.OK, respMp3.getStatusCode());
        assertEquals(MediaType.parseMediaType("audio/mpeg"), respMp3.getHeaders().getContentType());

        ResponseEntity<org.springframework.core.io.Resource> respMp4 = controller.file("avatar", "x.mp4");
        assertEquals(HttpStatus.OK, respMp4.getStatusCode());
        assertEquals(MediaType.parseMediaType("video/mp4"), respMp4.getHeaders().getContentType());

        ResponseEntity<org.springframework.core.io.Resource> respTxt = controller.file("image", "x.txt");
        assertEquals(HttpStatus.OK, respTxt.getStatusCode());
        assertEquals(MediaType.APPLICATION_OCTET_STREAM, respTxt.getHeaders().getContentType());
    }

    // 分支：file/路径为目录 -> 404
    @Test
    void fileDirectoryIs404() throws Exception {
        Path dir = tempDir.resolve("byok/image/subdir");
        Files.createDirectories(dir);
        ResponseEntity<org.springframework.core.io.Resource> resp = controller.file("image", "subdir");
        assertEquals(HttpStatus.NOT_FOUND, resp.getStatusCode());
    }
}
