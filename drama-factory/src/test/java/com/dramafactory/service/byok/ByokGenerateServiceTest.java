
package com.dramafactory.service.byok;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ByokGenerateService 单测：覆盖校验分支、供应商匹配、图片/音乐/数字人主路径、
 * 扩展名解析分支，以及 provider 名称 Map 的 null / 大小写分支。
 * 所有下载走注入的 DownloadSender 桩，不做真实网络请求。
 */
class ByokGenerateServiceTest {

    @TempDir
    Path tempDir;

    private MediaProviderRepository providerRepository;
    private ImageProvider imageProvider;
    private MusicProvider musicProvider;
    private AvatarProvider avatarProvider;

    @BeforeEach
    void setUp() {
        providerRepository = mock(MediaProviderRepository.class);
        imageProvider = mock(ImageProvider.class);
        musicProvider = mock(MusicProvider.class);
        avatarProvider = mock(AvatarProvider.class);
    }

    // ---------- 基础设施 helper ----------

    /** 构造一个 MediaProvider 并让 providerRepository.findById(1L) 返回它。 */
    private MediaProvider provider(String name) {
        MediaProvider p = new MediaProvider();
        p.setId(1L);
        p.setName(name);
        p.setApiKey("k");
        p.setApiAddress("https://api.example");
        when(providerRepository.findById(1L)).thenReturn(Optional.of(p));
        return p;
    }

    /** 构造 GenerateRequest。 */
    private ByokGenerateService.GenerateRequest req(String module, Map<String, String> options) {
        return new ByokGenerateService.GenerateRequest(module, 1L, "m1", "画一只猫", options);
    }

    /** 构造带注入 DownloadSender 的 service。 */
    private ByokGenerateService service(Path dir, ByokGenerateService.DownloadSender sender) {
        return new ByokGenerateService(
                providerRepository,
                Map.of("dashscope-image", imageProvider),
                Map.of("minimax-music", musicProvider),
                Map.of("did-avatar", avatarProvider),
                dir.toString(),
                sender);
    }

    /** 返回 statusCode=200、body 为给定内容的 HttpResponse 桩。 */
    @SuppressWarnings("unchecked")
    private ByokGenerateService.DownloadSender okSender(String body) {
        HttpResponse<InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(200);
        when(response.body()).thenReturn(new ByteArrayInputStream(body.getBytes()));
        return request -> response;
    }

    /** 返回 statusCode=code、body 为空的 HttpResponse 桩。 */
    @SuppressWarnings("unchecked")
    private ByokGenerateService.DownloadSender errSender(int code) {
        HttpResponse<InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(code);
        when(response.body()).thenReturn(new ByteArrayInputStream(new byte[0]));
        return request -> response;
    }

    // ---------- A. generate 校验分支（7 例） ----------

    @Test
    void generateShouldRejectNullRequest() {
        ByokGenerateService service = service(tempDir, okSender("x"));
        assertThrows(IllegalArgumentException.class, () -> service.generate(null));
    }

    @Test
    void generateShouldRejectNullModule() {
        provider("通义万相");
        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateRequest request =
                new ByokGenerateService.GenerateRequest(null, 1L, "m1", "画一只猫", Map.of());
        assertThrows(IllegalArgumentException.class, () -> service.generate(request));
    }

    @Test
    void generateShouldRejectUnsupportedModule() {
        provider("通义万相");
        ByokGenerateService service = service(tempDir, okSender("x"));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.generate(req("VIDEO", Map.of())));
        assertTrue(ex.getMessage().contains("不支持的模块"));
    }

    @Test
    void generateShouldRejectNullProviderId() {
        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateRequest request =
                new ByokGenerateService.GenerateRequest("IMAGE", null, "m1", "画一只猫", Map.of());
        assertThrows(IllegalArgumentException.class, () -> service.generate(request));
    }

    @Test
    void generateShouldRejectBlankModelId() {
        provider("通义万相");
        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateRequest request =
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "  ", "画一只猫", Map.of());
        assertThrows(IllegalArgumentException.class, () -> service.generate(request));
    }

    @Test
    void generateShouldRejectBlankPrompt() {
        provider("通义万相");
        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateRequest request =
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "  ", Map.of());
        assertThrows(IllegalArgumentException.class, () -> service.generate(request));
    }

    @Test
    void generateShouldThrowWhenProviderMissing() {
        when(providerRepository.findById(1L)).thenReturn(Optional.empty());
        ByokGenerateService service = service(tempDir, okSender("x"));
        assertThrows(ResourceNotFoundException.class,
                () -> service.generate(req("IMAGE", Map.of())));
    }

    // ---------- B. 匹配分支（4 例） ----------

    @Test
    void imageShouldRouteToDashscopeProvider() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/a.png", null, 100));

        ByokGenerateService service = service(tempDir, okSender("data"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("IMAGE", Map.of()));

        assertEquals("SUCCEEDED", resp.status());
        verify(imageProvider).submit(eq("k"), eq("https://api.example"), eq("m1"), eq("画一只猫"), anyString());
    }

    @Test
    void imageShouldThrowWhenProviderNotMatched() {
        provider("unknown-xyz");
        ByokGenerateService service = service(tempDir, okSender("x"));
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> service.generate(req("IMAGE", Map.of())));
        assertTrue(ex.getMessage().contains("暂未接入"));
    }

    @Test
    void musicShouldRouteToMinimaxProvider() {
        provider("MiniMax 音乐");
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), org.mockito.ArgumentMatchers.anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("http://cdn/x/a.mp3", 3000));

        ByokGenerateService service = service(tempDir, okSender("data"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("MUSIC", Map.of()));

        assertEquals("SUCCEEDED", resp.status());
        verify(musicProvider).generate(eq("k"), eq("https://api.example"), eq("m1"), eq("画一只猫"), any(), org.mockito.ArgumentMatchers.eq(false));
    }

    @Test
    void avatarShouldRequireImageUrl() {
        provider("D-ID 数字人");
        ByokGenerateService service = service(tempDir, okSender("x"));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.generate(req("AVATAR", Map.of())));
        assertTrue(ex.getMessage().contains("请提供人物图"));
    }

    // ---------- C. generateImage 主路径（6 例） ----------

    @Test
    void generateImageShouldSucceedAndPersistFile() throws Exception {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED,
                        "http://cdn/x/pic.JPG?token=1", null, 100));

        ByokGenerateService service = service(tempDir, okSender("img-bytes"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("IMAGE", Map.of()));

        assertEquals("SUCCEEDED", resp.status());
        assertTrue(resp.url().startsWith("/api/byok/file/image/"));
        assertTrue(resp.url().endsWith(".jpg"));

        Path stored = tempDir.resolve("byok").resolve("image")
                .resolve(resp.url().substring(resp.url().lastIndexOf('/') + 1));
        assertTrue(Files.exists(stored));
        assertEquals("img-bytes", Files.readString(stored));
    }

    @Test
    void generateImageShouldUseDefaultSize() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/a.png", null, 100));

        ByokGenerateService service = service(tempDir, okSender("x"));
        service.generate(req("IMAGE", Map.of()));

        ArgumentCaptor<String> sizeCaptor = ArgumentCaptor.forClass(String.class);
        verify(imageProvider).submit(anyString(), anyString(), anyString(), anyString(), sizeCaptor.capture());
        assertEquals("1024*1024", sizeCaptor.getValue());
    }

    @Test
    void generateImageShouldFailWhenPollFailed() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.FAILED, null, "boom", 0));

        ByokGenerateService service = service(tempDir, okSender("x"));
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.generate(req("IMAGE", Map.of())));
        assertTrue(ex.getMessage().contains("图片生成失败"));
    }

    @Test
    void generateImageShouldFailWhenUrlMissing() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "", null, 100));

        ByokGenerateService service = service(tempDir, okSender("x"));
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.generate(req("IMAGE", Map.of())));
        assertTrue(ex.getMessage().contains("未返回产物地址"));
    }

    @Test
    void generateImageShouldFailWhenDownloadReturns500() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/a.png", null, 100));

        ByokGenerateService service = service(tempDir, errSender(500));
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.generate(req("IMAGE", Map.of())));
        assertTrue(ex.getMessage().contains("HTTP 500"));
    }

    @Test
    void generateImageShouldSucceedAfterPolling() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.PROCESSING, null, null, 30))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/a.png", null, 100));

        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("IMAGE", Map.of()));

        assertEquals("SUCCEEDED", resp.status());
    }

    // ---------- D. resolveExtension 分支（3 例） ----------

    @Test
    void resolveExtensionShouldFallbackToHintWhenNoSuffix() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/pic", null, 100));

        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("IMAGE", Map.of()));

        assertTrue(resp.url().endsWith(".png"));
    }

    @Test
    void resolveExtensionShouldFallbackToBinWhenIllegalExt() {
        // 注：IMAGE 分支的 extHint 恒为 "png"（合法），因此非法后缀实际回退到 hint；
        // "bin" 分支在当前三个调用点均不可达（hint 恒合法），此处锁定真实行为
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/pic.exe", null, 100));

        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("IMAGE", Map.of()));

        assertTrue(resp.url().endsWith(".png"));
    }

    @Test
    void resolveExtensionShouldTruncateAtHash() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/a.mp4#frag", null, 100));

        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("IMAGE", Map.of()));

        assertTrue(resp.url().endsWith(".mp4"));
    }

    // ---------- E. generateMusic（3 例） ----------

    @Test
    void generateMusicShouldPassInstrumentalFlag() {
        provider("MiniMax 音乐");
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), org.mockito.ArgumentMatchers.anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("http://cdn/x/a.mp3", 3000));

        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("MUSIC", Map.of("instrumental", "true")));

        assertEquals("SUCCEEDED", resp.status());
        ArgumentCaptor<Boolean> instrumentalCaptor = ArgumentCaptor.forClass(Boolean.class);
        verify(musicProvider).generate(anyString(), anyString(), anyString(), anyString(), any(), instrumentalCaptor.capture());
        assertEquals(Boolean.TRUE, instrumentalCaptor.getValue());
    }

    @Test
    void generateMusicShouldFailWhenUrlMissing() {
        provider("MiniMax 音乐");
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), org.mockito.ArgumentMatchers.anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("", 3000));

        ByokGenerateService service = service(tempDir, okSender("x"));
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.generate(req("MUSIC", Map.of())));
        assertTrue(ex.getMessage().contains("未返回产物地址"));
    }

    @Test
    void generateMusicShouldSucceedWithLyrics() {
        provider("MiniMax 音乐");
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), org.mockito.ArgumentMatchers.anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("http://cdn/x/a.mp3", 3000));

        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateResponse resp = service.generate(req("MUSIC", Map.of("lyrics", "啦啦啦")));

        assertEquals("SUCCEEDED", resp.status());
        assertTrue(resp.url().endsWith(".mp3"));
    }

    // ---------- F. generateAvatar（3 例） ----------

    @Test
    void generateAvatarShouldSucceed() {
        provider("D-ID 数字人");
        when(avatarProvider.submit(anyString(), anyString(), any(), any()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(avatarProvider.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/v.mp4", null, 100));

        ByokGenerateService service = service(tempDir, okSender("x"));
        ByokGenerateService.GenerateResponse resp = service.generate(
                req("AVATAR", Map.of("imageUrl", "http://img/1.png")));

        assertEquals("SUCCEEDED", resp.status());
        assertTrue(resp.url().endsWith(".mp4"));
    }

    @Test
    void generateAvatarShouldFailWhenPollFailed() {
        provider("D-ID 数字人");
        when(avatarProvider.submit(anyString(), anyString(), any(), any()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(avatarProvider.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.FAILED, null, "boom", 0));

        ByokGenerateService service = service(tempDir, okSender("x"));
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.generate(req("AVATAR", Map.of("imageUrl", "http://img/1.png"))));
        assertTrue(ex.getMessage().contains("数字人生成失败"));
    }

    @Test
    void generateAvatarShouldFailWhenUrlMissing() {
        provider("D-ID 数字人");
        when(avatarProvider.submit(anyString(), anyString(), any(), any()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(avatarProvider.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.SUCCEEDED, "", null, 100));

        ByokGenerateService service = service(tempDir, okSender("x"));
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.generate(req("AVATAR", Map.of("imageUrl", "http://img/1.png"))));
        assertTrue(ex.getMessage().contains("未返回产物地址"));
    }

    // ---------- G. toNameMap 分支（2 例） ----------

    @Test
    void toNameMapShouldHandleNullMaps() {
        provider("通义万相");
        ByokGenerateService service = new ByokGenerateService(
                providerRepository, null, null, null, tempDir.toString(), okSender("x"));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> service.generate(req("IMAGE", Map.of())));
        assertTrue(ex.getMessage().contains("暂未接入"));
    }

    @Test
    void toNameMapShouldLowercaseKeys() {
        provider("通义万相");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, "http://cdn/x/a.png", null, 100));

        ByokGenerateService service = new ByokGenerateService(
                providerRepository,
                Map.of("DASHscope-IMAGE", imageProvider),
                Map.of(),
                Map.of(),
                tempDir.toString(),
                okSender("x"));

        ByokGenerateService.GenerateResponse resp = service.generate(req("IMAGE", Map.of()));
        assertEquals("SUCCEEDED", resp.status());
        assertNotNull(resp.url());
    }
}
