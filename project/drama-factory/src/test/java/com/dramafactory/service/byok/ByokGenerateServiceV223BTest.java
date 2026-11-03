package com.dramafactory.service.byok;

/*
 * 诚实跳过清单（经源码级论证不可达，不写测试）：
 * 1) ByokGenerateService.generate() 中 switch 的 default 分支（源码 L141 附近）：
 *    generate() 已在前面用 upperModule 校验 module 只可能是 IMAGE/MUSIC/AVATAR（L118 附近的 if），
 *    进入 switch 的 upperModule 必然命中三个 case 之一，default 分支不可达。
 * 2) generateImage 中图片轮询 deadline 分支（源码 L180 附近 `if (System.currentTimeMillis() >= deadline)`）：
 *    deadline 写死为 System.currentTimeMillis() + 150_000L，要触达该分支必须让 poll 持续返回非终态并真实
 *    sleep 150 秒以上（sleep 为 private static，无法注入替换），测试不可接受，判定不可达。
 * 3) generateAvatar 中数字人轮询 deadline 分支（源码 L253 附近 `if (System.currentTimeMillis() >= deadline)`）：
 *    deadline 写死为 System.currentTimeMillis() + 240_000L，同理需真实 sleep 240 秒，判定不可达。
 */

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.service.AssetService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.net.http.HttpResponse;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ByokGenerateServiceV223BTest {

    @TempDir
    java.nio.file.Path tempDir;

    @SuppressWarnings("unchecked")
    private static HttpResponse<InputStream> okResponse(byte[] bytes) {
        HttpResponse<InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(200);
        when(response.body()).thenReturn(new ByteArrayInputStream(bytes));
        return response;
    }

    @SuppressWarnings("unchecked")
    private static HttpResponse<InputStream> errorResponseWithFailingClose() {
        HttpResponse<InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(500);
        InputStream failingClose = new ByteArrayInputStream(new byte[0]) {
            @Override
            public void close() throws IOException {
                throw new IOException("boom");
            }
        };
        when(response.body()).thenReturn(failingClose);
        return response;
    }

    private MediaProvider provider(long id, String name) {
        MediaProvider p = new MediaProvider();
        p.setId(id);
        p.setName(name);
        p.setApiKey("k");
        p.setApiAddress("https://api.example");
        return p;
    }

    // L272 matchImage 的 contains 变体：全测一遍 + 完全不匹配返回 null
    @Test
    void matchImageCoversAllContainsVariants() {
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("dashscope-x"));
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("my-qwen-model"));
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("万相-provider"));
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("通义-provider"));
        assertEquals("dashscopeimageprovider", ByokGenerateService.matchImage("image-provider"));
        org.junit.jupiter.api.Assertions.assertNull(ByokGenerateService.matchImage("unknown-provider"));
    }

    // L296 matchAvatar 的 contains 变体：全测一遍 + 完全不匹配返回 null
    @Test
    void matchAvatarCoversAllContainsVariants() {
        assertEquals("didavatarprovider", ByokGenerateService.matchAvatar("d-id-x"));
        assertEquals("didavatarprovider", ByokGenerateService.matchAvatar("my-did-model"));
        assertEquals("didavatarprovider", ByokGenerateService.matchAvatar("数字人-provider"));
        org.junit.jupiter.api.Assertions.assertNull(ByokGenerateService.matchAvatar("unknown-provider"));
    }

    // L158 缺失臂：size="" 回落默认 "1024*1024"
    @Test
    void imageWithBlankSizeFallsBackToDefault() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope-test");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        ImageProvider.SubmitResult submitResult = new ImageProvider.SubmitResult("t1");
        when(imageProvider.submit(any(), any(), any(), any(), any())).thenReturn(submitResult);
        ImageProvider.PollResult pollResult = new ImageProvider.PollResult(
                ImageProvider.RemoteStatus.SUCCEEDED, "https://cdn.example/a.png", null, 100);
        when(imageProvider.poll(any(), any(), any())).thenReturn(pollResult);

        ByokGenerateService.DownloadSender sender =
                request -> okResponse("data".getBytes());

        ByokGenerateService svc = new ByokGenerateService(
                repo,
                Map.of("dashscopeimageprovider", imageProvider),
                Map.of(),
                Map.of(),
                tempDir.toString(),
                sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "IMAGE", 1L, "m1", "a cat", Map.of("size", ""));

        ByokGenerateService.GenerateResponse resp = svc.generate(req);

        assertEquals("SUCCEEDED", resp.status());

        ArgumentCaptor<String> sizeCaptor = ArgumentCaptor.forClass(String.class);
        verify(imageProvider).submit(eq("k"), eq("https://api.example"), eq("m1"), eq("a cat"), sizeCaptor.capture());
        assertEquals("1024*1024", sizeCaptor.getValue());
    }

    // L186 缺失臂：poll SUCCEEDED 但 imageUrl 为空串 -> RuntimeException("图片生成失败：未返回产物地址")
    @Test
    void imageWithBlankImageUrlThrows() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope-test");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        ImageProvider.SubmitResult submitResult = new ImageProvider.SubmitResult("t1");
        when(imageProvider.submit(any(), any(), any(), any(), any())).thenReturn(submitResult);
        ImageProvider.PollResult pollResult = new ImageProvider.PollResult(
                ImageProvider.RemoteStatus.SUCCEEDED, "", null, 100);
        when(imageProvider.poll(any(), any(), any())).thenReturn(pollResult);

        ByokGenerateService.DownloadSender sender =
                request -> okResponse("data".getBytes());

        ByokGenerateService svc = new ByokGenerateService(
                repo,
                Map.of("dashscopeimageprovider", imageProvider),
                Map.of(),
                Map.of(),
                tempDir.toString(),
                sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "IMAGE", 1L, "m1", "a cat", Map.of("size", "512*512"));

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(req));
        assertEquals("图片生成失败：未返回产物地址", ex.getMessage());
    }

    // L211 缺失臂：musicProvider.generate 返回 GenerateResult("", ...) -> RuntimeException("音乐生成失败：未返回产物地址")
    @Test
    void musicWithBlankAudioUrlThrows() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "minimax-test");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        MusicProvider musicProvider = mock(MusicProvider.class);
        MusicProvider.GenerateResult result = new MusicProvider.GenerateResult("", 1000);
        when(musicProvider.generate(any(), any(), any(), any(), any(), any(Boolean.class).booleanValue()))
                .thenReturn(result);

        ByokGenerateService.DownloadSender sender =
                request -> okResponse("data".getBytes());

        ByokGenerateService svc = new ByokGenerateService(
                repo,
                Map.of(),
                Map.of("minimaxmusicprovider", musicProvider),
                Map.of(),
                tempDir.toString(),
                sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "MUSIC", 1L, "m1", "a song", Map.of());

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(req));
        assertEquals("音乐生成失败：未返回产物地址", ex.getMessage());
    }

    // L259 缺失臂：poll SUCCEEDED 但 videoUrl 为空白 -> RuntimeException("数字人生成失败：未返回产物地址")
    @Test
    void avatarWithBlankVideoUrlThrows() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "d-id-test");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        AvatarProvider avatarProvider = mock(AvatarProvider.class);
        AvatarProvider.SubmitResult submitResult = new AvatarProvider.SubmitResult("talk1");
        when(avatarProvider.submit(any(), any(), any(), any())).thenReturn(submitResult);
        AvatarProvider.PollResult pollResult = new AvatarProvider.PollResult(
                AvatarProvider.RemoteStatus.SUCCEEDED, " ", null, 100);
        when(avatarProvider.poll(any(), any())).thenReturn(pollResult);

        ByokGenerateService.DownloadSender sender =
                request -> okResponse("data".getBytes());

        ByokGenerateService svc = new ByokGenerateService(
                repo,
                Map.of(),
                Map.of(),
                Map.of("didavatarprovider", avatarProvider),
                tempDir.toString(),
                sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "AVATAR", 1L, "m1", "hello", Map.of(
                        "imageUrl", "https://cdn.example/person.png",
                        "audioUrl", "https://cdn.example/voice.mp3"));

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(req));
        assertEquals("数字人生成失败：未返回产物地址", ex.getMessage());
    }

    // L334 缺失臂：statusCode=500 且 body.close() 抛 IOException -> RuntimeException("产物下载失败，HTTP 500")
    @Test
    void downloadDrainCloseIOExceptionThrowsHttp500() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope-test");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        ImageProvider.SubmitResult submitResult = new ImageProvider.SubmitResult("t1");
        when(imageProvider.submit(any(), any(), any(), any(), any())).thenReturn(submitResult);
        ImageProvider.PollResult pollResult = new ImageProvider.PollResult(
                ImageProvider.RemoteStatus.SUCCEEDED, "https://cdn.example/a.png", null, 100);
        when(imageProvider.poll(any(), any(), any())).thenReturn(pollResult);

        ByokGenerateService.DownloadSender sender =
                request -> errorResponseWithFailingClose();

        ByokGenerateService svc = new ByokGenerateService(
                repo,
                Map.of("dashscopeimageprovider", imageProvider),
                Map.of(),
                Map.of(),
                tempDir.toString(),
                sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "IMAGE", 1L, "m1", "a cat", Map.of("size", "512*512"));

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(req));
        assertTrue(ex.getMessage().contains("产物下载失败，HTTP 500"),
                "expected message contains HTTP 500 but was: " + ex.getMessage());
    }

    // L373 缺失臂：URL 带 #fragment -> resolveExtension 返回 "png"
    @Test
    void resolveExtensionHandlesHashFragment() throws Exception {
        Method m = ByokGenerateService.class.getDeclaredMethod("resolveExtension", String.class, String.class);
        m.setAccessible(true);
        Object result = m.invoke(null, "https://cdn.example/a.png#frag", null);
        assertEquals("png", result);
    }

    // L422 缺失臂：assetService==null 时 registerAsset 直接返回，不抛异常
    @Test
    void imageSuccessPathWithNullAssetServiceReturnsSucceeded() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider p = provider(1L, "dashscope-test");
        when(repo.findById(1L)).thenReturn(Optional.of(p));

        ImageProvider imageProvider = mock(ImageProvider.class);
        ImageProvider.SubmitResult submitResult = new ImageProvider.SubmitResult("t1");
        when(imageProvider.submit(any(), any(), any(), any(), any())).thenReturn(submitResult);
        ImageProvider.PollResult pollResult = new ImageProvider.PollResult(
                ImageProvider.RemoteStatus.SUCCEEDED, "https://cdn.example/a.png", null, 100);
        when(imageProvider.poll(any(), any(), any())).thenReturn(pollResult);

        ByokGenerateService.DownloadSender sender =
                request -> okResponse("data".getBytes());

        ByokGenerateService svc = new ByokGenerateService(
                repo,
                Map.of("dashscopeimageprovider", imageProvider),
                Map.of(),
                Map.of(),
                tempDir.toString(),
                sender);
        // 不调用 setAssetService，assetService 保持 null

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "IMAGE", 1L, "m1", "a cat", Map.of("size", "512*512"));

        ByokGenerateService.GenerateResponse resp = svc.generate(req);
        assertEquals("SUCCEEDED", resp.status());
        assertNotNull(resp.url());
    }

    // L429 缺失臂：文件不存在 -> size 参数为 0L
    @Test
    void registerAssetWithMissingFilePassesZeroSize() throws Exception {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);

        ByokGenerateService svc = new ByokGenerateService(
                repo,
                Map.of(),
                Map.of(),
                Map.of(),
                tempDir.toString(),
                request -> okResponse("data".getBytes()));

        AssetService assetService = mock(AssetService.class);
        svc.setAssetService(assetService);

        Method m = ByokGenerateService.class.getDeclaredMethod(
                "registerAsset",
                String.class,
                AssetType.class,
                Long.class,
                String.class,
                String.class);
        m.setAccessible(true);

        m.invoke(svc,
                "/api/byok/file/not-exist-xyz.png",
                AssetType.IMAGE,
                null,
                "dashscope-test",
                "a cat");

        verify(assetService).registerGenerated(
                eq("/api/byok/file/not-exist-xyz.png"),
                eq(AssetType.IMAGE),
                eq("image/png"),
                eq(0L),
                any(),
                any(),
                any());
    }
}
