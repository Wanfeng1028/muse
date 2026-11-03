package com.dramafactory.service.byok;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.LlmScriptService;
import com.dramafactory.service.MvLyricsService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.AbstractMap;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * v2.24 G 批：补剩余分支。dpsk 两轮输出均编造类名/签名，编排按已验证模式手工落盘。
 */
class ByokFixV224GTest {

    // 1. MiniMaxMusicProvider#generate 第 119 行 code<200→true 臂
    @Test
    void generate_http199_throwsRuntimeHttp199() throws Exception {
        CredentialResolver resolver = mock(CredentialResolver.class);
        ByokHttpGateway gateway = mock(ByokHttpGateway.class);
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>("Authorization", "Bearer test-key-123"));
        doReturn(new ByokHttpGateway.GatewayResponse(199, "x"))
                .when(gateway).exchange(any(HttpRequest.class));

        MiniMaxMusicProvider provider = new MiniMaxMusicProvider(resolver, new ObjectMapper(), gateway);
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.generate("k", "http://x", "music-01", "p", "la la la", false));
        assertTrue(ex.getMessage().contains("HTTP 199"), "实际=" + ex.getMessage());
    }

    private ByokGenerateService newService(String providerName,
                                           Map<String, ImageProvider> images,
                                           Map<String, MusicProvider> musics,
                                           Map<String, AvatarProvider> avatars) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider provider = mock(MediaProvider.class);
        when(repo.findById(1L)).thenReturn(Optional.of(provider));
        when(provider.getName()).thenReturn(providerName);
        when(provider.getApiKey()).thenReturn("k");
        when(provider.getApiAddress()).thenReturn("http://x");
        ByokGenerateService.DownloadSender sender = req -> {
            throw new AssertionError("不应走到下载");
        };
        return new ByokGenerateService(repo, images, musics, avatars, "./data/media", sender);
    }

    // 2. ByokGenerateService#generateMusic 第 211 行 audioUrl==null→true 臂
    @Test
    void generateMusic_nullAudioUrl_throwsUnreturnedProductAddress() {
        MusicProvider musicProvider = mock(MusicProvider.class);
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult(null, 1));
        ByokGenerateService service = newService("MiniMax 音乐", Map.of(),
                Map.of("minimaxmusicprovider", musicProvider), Map.of());
        RuntimeException ex = assertThrows(RuntimeException.class, () -> service.generate(
                new ByokGenerateService.GenerateRequest("MUSIC", 1L, "m", "p", Map.of())));
        assertEquals("音乐生成失败：未返回产物地址", ex.getMessage());
    }

    // 3. ByokGenerateService#generateImage 第 186 行 imageUrl==null→true 臂
    @Test
    void generateImage_nullImageUrl_throwsUnreturnedProductAddress() {
        ImageProvider imageProvider = mock(ImageProvider.class);
        when(imageProvider.submit(any(), any(), any(), any(), any()))
                .thenReturn(new ImageProvider.SubmitResult("t1"));
        when(imageProvider.poll(any(), any(), any()))
                .thenReturn(new ImageProvider.PollResult(
                        ImageProvider.RemoteStatus.SUCCEEDED, null, null, 100));
        ByokGenerateService service = newService("DashScope 图片",
                Map.of("dashscopeimageprovider", imageProvider), Map.of(), Map.of());
        RuntimeException ex = assertThrows(RuntimeException.class, () -> service.generate(
                new ByokGenerateService.GenerateRequest("IMAGE", 1L, "m", "p", Map.of("size", "512*512"))));
        assertEquals("图片生成失败：未返回产物地址", ex.getMessage());
    }

    // 4. ByokGenerateService#generateAvatar 第 259 行 videoUrl==null→true 臂
    @Test
    void generateAvatar_nullVideoUrl_throwsUnreturnedProductAddress() {
        AvatarProvider avatarProvider = mock(AvatarProvider.class);
        when(avatarProvider.submit(anyString(), anyString(), any(), any()))
                .thenReturn(new AvatarProvider.SubmitResult("t1"));
        when(avatarProvider.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(
                        AvatarProvider.RemoteStatus.SUCCEEDED, null, null, 100));
        ByokGenerateService service = newService("D-ID 数字人", Map.of(), Map.of(),
                Map.of("didavatarprovider", avatarProvider));
        RuntimeException ex = assertThrows(RuntimeException.class, () -> service.generate(
                new ByokGenerateService.GenerateRequest("AVATAR", 1L, "m", "p",
                        Map.of("imageUrl", "http://x/face.png", "audioUrl", "http://x/a.mp3"))));
        assertEquals("数字人生成失败：未返回产物地址", ex.getMessage());
    }

    // 6. ByokGenerateService#download 第 334 行 catch(IOException) 的"未进入 catch"臂：
    //    HTTP 500 + body 正常关闭 → drain 不抛 → 跳过 catch 直抛 HTTP 500。
    @Test
    void download_http500_normalClose_skipsCatchAndThrowsHttp500() {
        MusicProvider musicProvider = mock(MusicProvider.class);
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("http://x/a.mp3", 1));

        @SuppressWarnings("unchecked")
        HttpResponse<java.io.InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(500);
        when(response.body()).thenReturn(new java.io.ByteArrayInputStream(new byte[0]));

        ByokGenerateService.DownloadSender sender = req -> response;
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider provider = mock(MediaProvider.class);
        when(repo.findById(1L)).thenReturn(Optional.of(provider));
        when(provider.getName()).thenReturn("MiniMax 音乐");
        when(provider.getApiKey()).thenReturn("k");
        when(provider.getApiAddress()).thenReturn("http://x");
        ByokGenerateService service = new ByokGenerateService(repo, Map.of(),
                Map.of("minimaxmusicprovider", musicProvider), Map.of(), "./data/media", sender);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> service.generate(
                new ByokGenerateService.GenerateRequest("MUSIC", 1L, "m", "p", Map.of())));
        assertTrue(ex.getMessage().contains("产物下载失败，HTTP 500"), "实际=" + ex.getMessage());
    }

    // 5. MvLyricsService#stripFence 第 121 行 lastFence<0→false 臂
    @Test
    void stripFence_noClosingFence_returnsTrimmedRemainder() throws Exception {
        MvLyricsService service = new MvLyricsService(new ObjectMapper(), mock(LlmScriptService.class));
        Method m = MvLyricsService.class.getDeclaredMethod("stripFence", String.class);
        m.setAccessible(true);
        assertEquals("hello", m.invoke(service, "```json\nhello"));
    }

    /*
     * 诚实跳过清单（源码级论证不可达）：
     * - MiniMaxMusicProvider 第 138 行 audioUrl==null 臂：audioUrl 取自 root.path("data").path("audio").asText("")，asText("") 永不返回 null。
     * - MiniMaxMusicProvider 第 144 行 durationNode==null 臂：durationNode 取自 root.path(...).path(...)，path() 缺字段返回 MissingNode 永不 null。
     * - MvLyricsService 第 78 行 lyrics==null 臂：lyrics 取自 n.path("lyrics").asText("")，永不 null。
     * - ByokGenerateService 第 422 行 path==null 臂：registerAsset 的 path 参数来自 download() 返回值，恒为 "/api/byok/file/..." 非 null。
     * - ByokGenerateService 第 141 行 switch default / 180/253 行 deadline：v2.23 已论证（module 预校验 / 真实 sleep 150s+）。
     * - MvService 453/468/541/570、QuickToolsService 173/225/337、AceStepMusicProvider 83/142、DashScopeImageProvider 242、MvController 219/224：v2.23 及本轮已论证。
     */
}
