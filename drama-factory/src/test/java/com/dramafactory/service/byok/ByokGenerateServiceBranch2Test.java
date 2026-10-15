package com.dramafactory.service.byok;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.service.AssetService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ByokGenerateService 分支覆盖测试（第二批）。
 *
 * 诚实跳过清单（经分析确认无法在确定性单元测试中触达）：
 * 1. 行 92 sendViaClient：生产默认下载器走真实 JDK HttpClient，单元测试无法在不断网
 *    确定性的前提下触发；所有 download 相关测试均注入 DownloadSender 桩，故此分支不覆盖。
 * 2. 行 141 switch 的 default 臂（行 145）：generate() 入口（行 118）已校验 module 只能是
 *    IMAGE/MUSIC/AVATAR，default 为防御性代码，实际不可达。
 * 3. 行 180-181（图片轮询 150 秒超时）与 253-254（数字人 240 秒超时）：deadline 硬编码、
 *    无接缝注入，触发需真实等待数分钟，跳过。
 * 4. 行 306-308 sleep() 的 InterruptedException：无法确定性地中断当前线程并断言，跳过。
 * 5. 行 429 Files.exists(p) 为 false 的臂：p 对应的文件刚由 download() 写入，实践中恒为 true。
 * 6. 行 373 resolveExtension 的 slashIdx<0 臂（lastSegment=path 全体）：download()（唯一调用方）
 *    先经 JDK HttpRequest.newBuilder().uri() 校验，实测无 scheme://authority 的 URI 一律抛
 *    IllegalArgumentException（"https:file.png"/"https:/file.png" 均被拒，仅 "https://…" 形
 *    式通过）；能到达 resolveExtension 的 URL 必含 '/'，该臂为防御性不可达，不硬编测试。
 */
class ByokGenerateServiceBranch2Test {

    private static final String IMG_BEAN = "dashscopeimageprovider";
    private static final String MUSIC_BEAN = "minimaxmusicprovider";
    private static final String AVATAR_BEAN = "didavatarprovider";

    // ---------------- helpers ----------------

    private MediaProvider provider(Long id, String name) {
        MediaProvider p = new MediaProvider();
        p.setId(id);
        p.setName(name);
        p.setApiKey("k");
        p.setApiAddress("http://api");
        return p;
    }

    private HttpResponse<InputStream> resp(int code, byte[] bytes) {
        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> r = mock(HttpResponse.class);
        when(r.statusCode()).thenReturn(code);
        when(r.body()).thenReturn(new ByteArrayInputStream(bytes == null ? new byte[0] : bytes));
        return r;
    }

    private ByokGenerateService newService(MediaProviderRepository repo,
                                           Map<String, ImageProvider> imageProviders,
                                           Map<String, MusicProvider> musicProviders,
                                           Map<String, AvatarProvider> avatarProviders,
                                           String storageDir,
                                           ByokGenerateService.DownloadSender sender) {
        return new ByokGenerateService(repo, imageProviders, musicProviders, avatarProviders, storageDir, sender);
    }

    private MediaProviderRepository repoReturning(MediaProvider p) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        when(repo.findById(p.getId())).thenReturn(Optional.of(p));
        return repo;
    }

    private ImageProvider imageProviderSucceeding(String url) {
        ImageProvider ip = mock(ImageProvider.class);
        when(ip.submit(anyString(), anyString(), anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(ip.poll(anyString(), anyString(), anyString()))
                .thenReturn(new ImageProvider.PollResult(ImageProvider.RemoteStatus.SUCCEEDED, url, null, 100));
        return ip;
    }

    // ---------------- 图片流 ----------------

    // T1: 行 158 —— size 为空串 "" 的臂，回退到 "1024*1024"
    @Test
    void imageBlankSize_expectsFallbackToDefaultSize(@TempDir Path tmp) {
        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/a.png");
        Map<String, ImageProvider> imgs = Map.of(IMG_BEAN, ip);
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, imgs, Map.of(), Map.of(), tmp.toString(), sender);

        Map<String, String> opts = new HashMap<>();
        opts.put("size", "");
        ByokGenerateService.GenerateResponse r = svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", opts));

        assertEquals("SUCCEEDED", r.status());
        ArgumentCaptor<String> sizeCap = ArgumentCaptor.forClass(String.class);
        verify(ip).submit(anyString(), anyString(), anyString(), anyString(), sizeCap.capture());
        assertEquals("1024*1024", sizeCap.getValue());
    }

    // T2: 行 186 —— imageUrl 为空串的臂
    @Test
    void imageEmptyUrl_expectsRuntimeException() {
        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("");
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(), "unused", sender);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of())));
        assertTrue(ex.getMessage().contains("未返回产物地址"));
    }

    // ---------------- 音乐流 ----------------

    // T3: 行 198 —— beanName 非空但 map.get 返回 null 的臂
    @Test
    void musicBeanMatchedButNotRegistered_expectsIllegalState() {
        MediaProvider p = provider(1L, "minimax-pro");
        MediaProviderRepository repo = repoReturning(p);
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(), Map.of(), Map.of(), "unused", sender);

        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("MUSIC", 1L, "m1", "prompt", Map.of())));
        assertTrue(ex.getMessage().contains("暂未接入"));
    }

    // T4: 行 211 —— audioUrl 为空串的臂
    @Test
    void musicEmptyAudioUrl_expectsRuntimeException() {
        MediaProvider p = provider(1L, "minimax");
        MediaProviderRepository repo = repoReturning(p);
        MusicProvider mp = mock(MusicProvider.class);
        when(mp.generate(anyString(), anyString(), anyString(), anyString(), any(), org.mockito.ArgumentMatchers.anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("", 100));
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(), Map.of(MUSIC_BEAN, mp), Map.of(), "unused", sender);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("MUSIC", 1L, "m1", "prompt", Map.of())));
        assertTrue(ex.getMessage().contains("未返回产物地址"));
    }

    // ---------------- 数字人流 ----------------

    // T5: 行 223 —— beanName 非空但 map.get 返回 null 的臂
    @Test
    void avatarBeanMatchedButNotRegistered_expectsIllegalState() {
        MediaProvider p = provider(1L, "d-id-pro");
        MediaProviderRepository repo = repoReturning(p);
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(), Map.of(), Map.of(), "unused", sender);

        Map<String, String> opts = new HashMap<>();
        opts.put("imageUrl", "http://img/a.png");
        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m1", "prompt", opts)));
        assertTrue(ex.getMessage().contains("暂未接入"));
    }

    // T6: 行 250 —— poll FAILED 的臂
    @Test
    void avatarPollFailed_expectsRuntimeException() {
        MediaProvider p = provider(1L, "d-id");
        MediaProviderRepository repo = repoReturning(p);
        AvatarProvider ap = mock(AvatarProvider.class);
        when(ap.submit(anyString(), anyString(), any(), anyString()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(ap.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.FAILED, null, "quota exceeded", 0));
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(), Map.of(), Map.of(AVATAR_BEAN, ap), "unused", sender);

        Map<String, String> opts = new HashMap<>();
        opts.put("imageUrl", "http://img/a.png");
        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m1", "prompt", opts)));
        assertTrue(ex.getMessage().contains("数字人生成失败"));
    }

    // T7: 行 256 —— sleep(5000L) 指令；poll PROCESSING 后 SUCCEEDED
    @Test
    void avatarPollProcessingThenSucceeded_expectsSuccess(@TempDir Path tmp) {
        MediaProvider p = provider(1L, "d-id");
        MediaProviderRepository repo = repoReturning(p);
        AvatarProvider ap = mock(AvatarProvider.class);
        when(ap.submit(anyString(), anyString(), any(), anyString()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(ap.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.PROCESSING, null, null, 10))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.SUCCEEDED, "http://x/v.mp4", null, 100));
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(), Map.of(), Map.of(AVATAR_BEAN, ap), tmp.toString(), sender);

        Map<String, String> opts = new HashMap<>();
        opts.put("imageUrl", "http://img/a.png");
        ByokGenerateService.GenerateResponse r = svc.generate(
                new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m1", "prompt", opts));
        assertEquals("SUCCEEDED", r.status());
        verify(ap, times(2)).poll(anyString(), anyString());
    }

    // T8: 行 259 —— videoUrl 为空串的臂
    @Test
    void avatarEmptyVideoUrl_expectsRuntimeException() {
        MediaProvider p = provider(1L, "d-id");
        MediaProviderRepository repo = repoReturning(p);
        AvatarProvider ap = mock(AvatarProvider.class);
        when(ap.submit(anyString(), anyString(), any(), anyString()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(ap.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.SUCCEEDED, "", null, 100));
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(), Map.of(), Map.of(AVATAR_BEAN, ap), "unused", sender);

        Map<String, String> opts = new HashMap<>();
        opts.put("imageUrl", "http://img/a.png");
        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m1", "prompt", opts)));
        assertTrue(ex.getMessage().contains("未返回产物地址"));
    }

    // ---------------- match 方法 ----------------

    // T9: 行 272 —— "通义"/"万相" 臂
    @Test
    void matchImageTongyiAndWanxiang_expectsDashscopeBean() {
        assertEquals(IMG_BEAN, ByokGenerateService.matchImage("通义万相pro"));
        assertEquals(IMG_BEAN, ByokGenerateService.matchImage("万相平台"));
    }

    // T10: 行 296 —— "数字人" 臂
    @Test
    void matchAvatarDigitalHuman_expectsDidBean() {
        assertEquals(AVATAR_BEAN, ByokGenerateService.matchAvatar("数字人平台"));
    }

    // ---------------- download() ----------------

    // T11: 行 323-324 —— DownloadSender 抛 IOException 的臂
    @Test
    void downloadSenderThrowsIoException_expectsDownloadFailure() {
        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/a.png");
        ByokGenerateService.DownloadSender sender = req -> { throw new IOException("conn reset"); };
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(), "unused", sender);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of())));
        assertTrue(ex.getMessage().contains("产物下载失败"));
    }

    // T12: 行 325-327 —— DownloadSender 抛 InterruptedException 的臂
    @Test
    void downloadSenderThrowsInterruptedException_expectsInterruptedMessage() {
        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/a.png");
        ByokGenerateService.DownloadSender sender = req -> { throw new InterruptedException("intr"); };
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(), "unused", sender);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of())));
        assertTrue(ex.getMessage().contains("生成被中断"));
    }

    // T13: 行 334 —— drain 时 body.close() 抛 IOException 被吞的臂
    @Test
    void downloadHttp500AndCloseThrows_expectsHttp500Message() throws IOException {
        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/a.png");

        InputStream bodyMock = mock(InputStream.class);
        doThrow(new IOException("x")).when(bodyMock).close();

        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(500);
        when(resp.body()).thenReturn(bodyMock);

        ByokGenerateService.DownloadSender sender = req -> resp;
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(), "unused", sender);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of())));
        assertTrue(ex.getMessage().contains("产物下载失败，HTTP 500"));
    }

    // T14: 行 346-347 —— createDirectories 抛 IOException 的臂（storageDir 是已存在的普通文件）
    @Test
    void createDirectoriesFails_expectsDownloadFailure(@TempDir Path tmp) throws IOException {
        Path asFile = tmp.resolve("not-a-dir");
        Files.createFile(asFile);

        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/a.png");
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(),
                asFile.toString(), sender);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of())));
        assertTrue(ex.getMessage().contains("产物下载失败"));
    }

    // T15: 行 353-354 —— Files.copy 抛 IOException 的臂
    @Test
    void filesCopyFails_expectsDownloadFailure(@TempDir Path tmp) {
        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/a.png");

        InputStream boom = new InputStream() {
            @Override
            public int read() throws IOException {
                throw new IOException("read boom");
            }
        };
        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(200);
        when(resp.body()).thenReturn(boom);

        ByokGenerateService.DownloadSender sender = req -> resp;
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(),
                tmp.toString(), sender);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of())));
        assertTrue(ex.getMessage().contains("产物下载失败"));
    }

    // T16: 行 373 slashIdx<0 臂——见文件顶部诚实跳过清单第 6 条：经实测该臂防御性不可达，
    // 不硬编测试（dpsk 原 T16 用裸 "file.png"/"https:file.png" 均在 JDK HttpRequest.uri()
    // 校验处先抛 IllegalArgumentException，到不了 resolveExtension）。

    // T17: 行 375 —— dotIdx == lastSegment.length()-1（末尾是点号）的臂，走 extHint
    @Test
    void urlEndingWithDot_expectsHintExtension(@TempDir Path tmp) {
        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/file.");
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[]{1, 2, 3});
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(),
                tmp.toString(), sender);

        ByokGenerateService.GenerateResponse r = svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of()));
        assertEquals("SUCCEEDED", r.status());
        assertTrue(r.url().endsWith(".png"));
    }

    // ---------------- registerAsset() ----------------

    // T18: 行 422/427/428 —— assetService 非空，IMAGE 流注册
    @Test
    void registerAssetImage_expectsImagePngMime(@TempDir Path tmp) {
        MediaProvider p = provider(1L, "qwen");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/a.png");
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[]{1, 2, 3});
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(),
                tmp.toString(), sender);

        AssetService assetService = mock(AssetService.class);
        svc.setAssetService(assetService);

        ByokGenerateService.GenerateResponse r = svc.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of()));
        assertEquals("SUCCEEDED", r.status());

        ArgumentCaptor<String> mimeCap = ArgumentCaptor.forClass(String.class);
        verify(assetService).registerGenerated(anyString(), any(), mimeCap.capture(),
                org.mockito.ArgumentMatchers.anyLong(), anyString(), anyString(), any());
        assertEquals("image/png", mimeCap.getValue());
    }

    // T19: 行 427 —— AUDIO 臂
    @Test
    void registerAssetAudio_expectsAudioMpegMime(@TempDir Path tmp) {
        MediaProvider p = provider(1L, "minimax");
        MediaProviderRepository repo = repoReturning(p);
        MusicProvider mp = mock(MusicProvider.class);
        when(mp.generate(anyString(), anyString(), anyString(), anyString(), any(), org.mockito.ArgumentMatchers.anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("http://x/a.mp3", 1000));
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[]{1, 2, 3});
        ByokGenerateService svc = newService(repo, Map.of(), Map.of(MUSIC_BEAN, mp), Map.of(),
                tmp.toString(), sender);

        AssetService assetService = mock(AssetService.class);
        svc.setAssetService(assetService);

        ByokGenerateService.GenerateResponse r = svc.generate(
                new ByokGenerateService.GenerateRequest("MUSIC", 1L, "m1", "prompt", Map.of()));
        assertEquals("SUCCEEDED", r.status());

        ArgumentCaptor<String> mimeCap = ArgumentCaptor.forClass(String.class);
        verify(assetService).registerGenerated(anyString(), any(), mimeCap.capture(),
                org.mockito.ArgumentMatchers.anyLong(), anyString(), anyString(), any());
        assertEquals("audio/mpeg", mimeCap.getValue());
    }

    // T20: 行 427 —— VIDEO 臂
    @Test
    void registerAssetVideo_expectsVideoMp4Mime(@TempDir Path tmp) {
        MediaProvider p = provider(1L, "d-id");
        MediaProviderRepository repo = repoReturning(p);
        AvatarProvider ap = mock(AvatarProvider.class);
        when(ap.submit(anyString(), anyString(), any(), anyString()))
                .thenReturn(new AvatarProvider.SubmitResult("talk1"));
        when(ap.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(AvatarProvider.RemoteStatus.SUCCEEDED, "http://x/v.mp4", null, 100));
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[]{1, 2, 3});
        ByokGenerateService svc = newService(repo, Map.of(), Map.of(), Map.of(AVATAR_BEAN, ap),
                tmp.toString(), sender);

        AssetService assetService = mock(AssetService.class);
        svc.setAssetService(assetService);

        Map<String, String> opts = new HashMap<>();
        opts.put("imageUrl", "http://img/a.png");
        ByokGenerateService.GenerateResponse r = svc.generate(
                new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m1", "prompt", opts));
        assertEquals("SUCCEEDED", r.status());

        ArgumentCaptor<String> mimeCap = ArgumentCaptor.forClass(String.class);
        verify(assetService).registerGenerated(anyString(), any(), mimeCap.capture(),
                org.mockito.ArgumentMatchers.anyLong(), anyString(), anyString(), any());
        assertEquals("video/mp4", mimeCap.getValue());
    }

    // 补充：ImageProvider 提交参数捕获（确保 HttpRequest 未被真实发送）
    @Test
    void imageSubmitUsesMockProvider_expectsNoRealNetwork(@TempDir Path tmp) {
        MediaProvider p = provider(1L, "dashscope");
        MediaProviderRepository repo = repoReturning(p);
        ImageProvider ip = imageProviderSucceeding("http://x/a.png");
        ByokGenerateService.DownloadSender sender = req -> resp(200, new byte[0]);
        ByokGenerateService svc = newService(repo, Map.of(IMG_BEAN, ip), Map.of(), Map.of(), tmp.toString(), sender);

        svc.generate(new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m1", "prompt", Map.of()));

        verify(ip).submit(eq("k"), eq("http://api"), eq("m1"), eq("prompt"), anyString());
    }
}
