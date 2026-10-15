package com.dramafactory.service.byok;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * ByokGenerateService 分支收尾测试（第三批）。
 *
 * 诚实跳过清单：
 * 1. 422 行 registerAsset 的 {@code path == null} 臂：防御性不可达。path 恒为 download(...)
 *    的返回值，而 download 只在正常路径返回 {@code "/api/byok/file/..."}，从不返回 null，
 *    无法在真实执行路径上触达该分支，故跳过。
 * 2. 422 行 registerAsset 的 {@code assetService == null} 臂：已有旧测试 T1~T17 覆盖
 *    （均未调用 setAssetService），本轮不再重复编写。
 * 3. 141 行 switch 的 default 臂：module 入口已在第 118 行校验只能为 IMAGE/MUSIC/AVATAR，
 *    default 防御性不可达（已由 ByokGenerateServiceBranch2Test 诚实跳过清单第 2 条记录）。
 * 4. 180 行 generateImage 的 deadline 超时臂、253 行 generateAvatar 的 deadline 超时臂：
 *    依赖真实时间流逝（150s / 240s），单测不可控，已由 ByokGenerateServiceBranch2Test
 *    诚实跳过清单记录，本轮沿用说明。
 * 5. 373 行 resolveExtension 的 {@code slashIdx < 0} 臂：JDK HttpRequest 对 URI 的校验保证
 *    传入 download 的 URL 必含 '/'（download 内 URI.create(url) 会拒绝无 '/' 的相对形式），
 *    该分支不可达，已由 ByokGenerateServiceBranch2Test 诚实跳过清单记录，本轮沿用说明。
 * 6. 429 行 registerAsset 内 Files.exists/size 的异常臂：依赖测试机文件系统状态，
 *    已由 ByokGenerateServiceBranch2Test 诚实跳过清单记录，本轮沿用说明。
 */
class ByokGenerateServiceBranch3Test {

    @TempDir
    Path tempDir;

    private MediaProviderRepository providerRepository;
    private ByokGenerateService.DownloadSender sender;

    @BeforeEach
    void setUp() {
        providerRepository = mock(MediaProviderRepository.class);
        sender = mock(ByokGenerateService.DownloadSender.class);
    }

    private MediaProvider providerNamed(long id, String name) {
        MediaProvider p = new MediaProvider();
        p.setId(id);
        p.setName(name);
        p.setApiKey("k");
        p.setApiAddress("https://api.example.com");
        when(providerRepository.findById(id)).thenReturn(Optional.of(p));
        return p;
    }

    private HttpResponse<InputStream> okResponse(String body) {
        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(200);
        when(resp.body()).thenReturn(new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8)));
        return resp;
    }

    private ImageProvider.PollResult pollSucceeded(String imageUrl) {
        ImageProvider.PollResult pr = mock(ImageProvider.PollResult.class);
        when(pr.status()).thenReturn(ImageProvider.RemoteStatus.SUCCEEDED);
        when(pr.imageUrl()).thenReturn(imageUrl);
        return pr;
    }

    /**
     * 覆盖 generateImage 第 158 行 if (size == null || size.isBlank()) 的 blank 臂：
     * options.get("size") 为 "" → 默认 "1024*1024" 传入 submit 第 5 参。
     */
    @Test
    void generateImage_blankSize_expectsDefaultSize() throws Exception {
        MediaProvider p = providerNamed(1L, "通义万相");
        ImageProvider imageProvider = mock(ImageProvider.class);
        ImageProvider.SubmitResult submitResult = mock(ImageProvider.SubmitResult.class);
        when(submitResult.taskId()).thenReturn("t-1");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(submitResult);
        ImageProvider.PollResult pr = pollSucceeded("https://x/i.png");
        when(imageProvider.poll(anyString(), anyString(), anyString())).thenReturn(pr);
        HttpResponse<InputStream> dlResp = okResponse("PNGDATA");
        when(sender.send(any(HttpRequest.class))).thenReturn(dlResp);

        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(),
                tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "IMAGE", 1L, "m", "p", Map.of("size", ""));

        ByokGenerateService.GenerateResponse resp = svc.generate(req);

        assertEquals("SUCCEEDED", resp.status());
        ArgumentCaptor<String> sizeCaptor = ArgumentCaptor.forClass(String.class);
        org.mockito.Mockito.verify(imageProvider)
                .submit(anyString(), anyString(), anyString(), anyString(), sizeCaptor.capture());
        assertEquals("1024*1024", sizeCaptor.getValue());
    }

    /**
     * 覆盖 generateImage 第 186 行 if (imageUrl == null || imageUrl.isBlank()) 的 blank 臂：
     * poll 返回 SUCCEEDED 但 imageUrl 为 "" → 抛 "图片生成失败：未返回产物地址"。
     */
    @Test
    void generateImage_blankImageUrl_expectsRuntimeException() {
        providerNamed(1L, "通义万相");
        ImageProvider imageProvider = mock(ImageProvider.class);
        ImageProvider.SubmitResult submitResult = mock(ImageProvider.SubmitResult.class);
        when(submitResult.taskId()).thenReturn("t-1");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(submitResult);
        ImageProvider.PollResult pr = pollSucceeded("");
        when(imageProvider.poll(anyString(), anyString(), anyString())).thenReturn(pr);

        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(),
                tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "IMAGE", 1L, "m", "p", Map.of());

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(req));
        assertTrue(ex.getMessage().contains("未返回产物地址"), "实际消息: " + ex.getMessage());
    }

    /**
     * 覆盖 matchMusic 返回 null 的臂（第 198 行）：provider name="qwen" 不含 minimax/ace-step
     * → 抛 IllegalStateException("该供应商暂未接入生成实现：...")。
     */
    @Test
    void generateMusic_unmatchedProvider_expectsIllegalStateException() {
        providerNamed(2L, "qwen");
        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of(), Map.of(), Map.of(), tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "MUSIC", 2L, "m", "p", Map.of());

        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> svc.generate(req));
        assertTrue(ex.getMessage().contains("暂未接入生成实现"), "实际消息: " + ex.getMessage());
    }

    /**
     * 覆盖 generateMusic 第 211 行 if (audioUrl == null || audioUrl.isBlank()) 的 blank 臂：
     * musicProvider.generate 返回 audioUrl="" → 抛 "音乐生成失败：未返回产物地址"。
     */
    @Test
    void generateMusic_blankAudioUrl_expectsRuntimeException() {
        providerNamed(3L, "minimax");
        MusicProvider musicProvider = mock(MusicProvider.class);
        MusicProvider.GenerateResult genResult = mock(MusicProvider.GenerateResult.class);
        when(genResult.audioUrl()).thenReturn("");
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(),
                any(), anyBoolean())).thenReturn(genResult);

        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of(), Map.of("minimaxmusicprovider", musicProvider), Map.of(),
                tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "MUSIC", 3L, "m", "p", Map.of());

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(req));
        assertTrue(ex.getMessage().contains("未返回产物地址"), "实际消息: " + ex.getMessage());
    }

    /**
     * 覆盖 matchAvatar 返回 null 的臂（第 223 行）：provider name="qwen" 不含 d-id/did/数字人
     * → 抛 IllegalStateException("该供应商暂未接入生成实现：...")。
     */
    @Test
    void generateAvatar_unmatchedProvider_expectsIllegalStateException() {
        providerNamed(4L, "qwen");
        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of(), Map.of(), Map.of(), tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "AVATAR", 4L, "m", "p", Map.of("imageUrl", "https://x/a.png"));

        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> svc.generate(req));
        assertTrue(ex.getMessage().contains("暂未接入生成实现"), "实际消息: " + ex.getMessage());
    }

    /**
     * 覆盖 generateAvatar 第 259 行 if (videoUrl == null || videoUrl.isBlank()) 的 blank 臂：
     * poll 返回 SUCCEEDED 但 videoUrl 为 "" → 抛 "数字人生成失败：未返回产物地址"。
     */
    @Test
    void generateAvatar_blankVideoUrl_expectsRuntimeException() {
        providerNamed(5L, "数字人服务");
        AvatarProvider avatarProvider = mock(AvatarProvider.class);
        AvatarProvider.SubmitResult submitResult = mock(AvatarProvider.SubmitResult.class);
        when(submitResult.talkId()).thenReturn("talk-1");
        when(avatarProvider.submit(anyString(), anyString(), any(), anyString())).thenReturn(submitResult);
        AvatarProvider.PollResult pollResult = mock(AvatarProvider.PollResult.class);
        when(pollResult.status()).thenReturn(AvatarProvider.RemoteStatus.SUCCEEDED);
        when(pollResult.videoUrl()).thenReturn("");
        when(avatarProvider.poll(anyString(), anyString())).thenReturn(pollResult);

        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of(), Map.of(), Map.of("didavatarprovider", avatarProvider),
                tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "AVATAR", 5L, "m", "p", Map.of("imageUrl", "https://x/a.png"));

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(req));
        assertTrue(ex.getMessage().contains("未返回产物地址"), "实际消息: " + ex.getMessage());
    }

    /**
     * 覆盖 matchImage 的 || 链第 272 行 "万相"/"通义" 臂：provider name="通义万相" →
     * 匹配到 dashscopeimageprovider，generate 走通成功。
     */
    @Test
    void generateImage_matchesTongyiWanxiang_expectsSuccess() throws Exception {
        providerNamed(6L, "通义万相");
        ImageProvider imageProvider = mock(ImageProvider.class);
        ImageProvider.SubmitResult submitResult = mock(ImageProvider.SubmitResult.class);
        when(submitResult.taskId()).thenReturn("t-6");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(submitResult);
        ImageProvider.PollResult pr = pollSucceeded("https://x/i.png");
        when(imageProvider.poll(anyString(), anyString(), anyString())).thenReturn(pr);
        HttpResponse<InputStream> dlResp = okResponse("PNGDATA");
        when(sender.send(any(HttpRequest.class))).thenReturn(dlResp);

        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(),
                tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "IMAGE", 6L, "m", "p", Map.of());

        ByokGenerateService.GenerateResponse resp = svc.generate(req);

        assertEquals("SUCCEEDED", resp.status());
        assertTrue(resp.url().startsWith("/api/byok/file/image/"));
    }

    /**
     * 覆盖 matchAvatar 的 || 链第 296 行 "数字人" 臂：provider name="数字人服务" →
     * 匹配到 didavatarprovider，generate 走通成功。
     */
    @Test
    void generateAvatar_matchesDigitalHuman_expectsSuccess() throws Exception {
        providerNamed(7L, "数字人服务");
        AvatarProvider avatarProvider = mock(AvatarProvider.class);
        AvatarProvider.SubmitResult submitResult = mock(AvatarProvider.SubmitResult.class);
        when(submitResult.talkId()).thenReturn("talk-7");
        when(avatarProvider.submit(anyString(), anyString(), any(), anyString())).thenReturn(submitResult);
        AvatarProvider.PollResult pollResult = mock(AvatarProvider.PollResult.class);
        when(pollResult.status()).thenReturn(AvatarProvider.RemoteStatus.SUCCEEDED);
        when(pollResult.videoUrl()).thenReturn("https://x/v.mp4");
        when(avatarProvider.poll(anyString(), anyString())).thenReturn(pollResult);
        HttpResponse<InputStream> dlResp = okResponse("MP4DATA");
        when(sender.send(any(HttpRequest.class))).thenReturn(dlResp);

        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of(), Map.of(), Map.of("didavatarprovider", avatarProvider),
                tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "AVATAR", 7L, "m", "p", Map.of("imageUrl", "https://x/a.png"));

        ByokGenerateService.GenerateResponse resp = svc.generate(req);

        assertEquals("SUCCEEDED", resp.status());
        assertTrue(resp.url().startsWith("/api/byok/file/avatar/"));
    }

    /**
     * 覆盖 download 第 334 行 drain 时 close() 抛 IOException 的臂：非 2xx 时关闭 body
     * 流抛 IOException 会被吞掉，随后仍抛 "产物下载失败，HTTP 500"。
     */
    @Test
    void download_non2xxAndCloseThrows_expectsDownloadFailure() throws Exception {
        providerNamed(8L, "通义万相");
        ImageProvider imageProvider = mock(ImageProvider.class);
        ImageProvider.SubmitResult submitResult = mock(ImageProvider.SubmitResult.class);
        when(submitResult.taskId()).thenReturn("t-8");
        when(imageProvider.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(submitResult);
        ImageProvider.PollResult pr = pollSucceeded("https://x/i.png");
        when(imageProvider.poll(anyString(), anyString(), anyString())).thenReturn(pr);

        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(500);
        InputStream body = mock(InputStream.class);
        doThrow(new IOException("close-boom")).when(body).close();
        when(resp.body()).thenReturn(body);
        when(sender.send(any(HttpRequest.class))).thenReturn(resp);

        ByokGenerateService svc = new ByokGenerateService(providerRepository,
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of(),
                tempDir.toString(), sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "IMAGE", 8L, "m", "p", Map.of());

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(req));
        assertTrue(ex.getMessage().contains("产物下载失败，HTTP 500"),
                "实际消息: " + ex.getMessage());
    }
}
