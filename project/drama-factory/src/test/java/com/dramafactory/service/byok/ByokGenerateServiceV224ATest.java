package com.dramafactory.service.byok;

import com.dramafactory.model.MediaProvider;
import com.dramafactory.repository.MediaProviderRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;

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
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * 针对 ByokGenerateService 的分支覆盖补充测试（V224A）。
 *
 * 覆盖目标（JaCoCo 实测未覆盖分支）：
 * 1. generateMusic 第 199 行 musicProvider == null 的 true 臂。
 * 2. generateMusic 第 208 行 audioUrl.isBlank() 的 true 臂。
 * 3. generateAvatar 第 250 行 status == FAILED 的 true 臂。
 * 4. download 第 334 行 catch (IOException ignored) 臂（drain 时 body.close() 抛 IOException）。
 * 5. resolveExtension 第 373 行 slashIdx < 0 时取 path 臂。
 * 6. registerAsset 第 422 行 assetService == null 提前返回臂。
 */
class ByokGenerateServiceV224ATest {

    // ---------------------------------------------------------------------
    // 用例 1：generateMusic 中 musicProvider == null 的 true 臂
    // ---------------------------------------------------------------------
    @Test
    void generateMusic_musicProviderNull_throwsIllegalStateWithProviderName() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider provider = mock(MediaProvider.class);
        when(repo.findById(1L)).thenReturn(Optional.of(provider));
        // "未知供应商" 不含 minimax / ace-step / acestep，matchMusic 返回 null
        when(provider.getName()).thenReturn("未知供应商");
        lenient().when(provider.getApiKey()).thenReturn("k");
        lenient().when(provider.getApiAddress()).thenReturn("http://x");

        ByokGenerateService.DownloadSender sender = req -> {
            throw new AssertionError("不应走到下载");
        };

        ByokGenerateService service = new ByokGenerateService(
                repo, Map.of(), Map.of(), Map.of(), "./data/media", sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "MUSIC", 1L, "m", "p", Map.of());

        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> service.generate(req));
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().startsWith("该供应商暂未接入生成实现："),
                "实际消息：" + ex.getMessage());
    }

    // ---------------------------------------------------------------------
    // 用例 2：generateMusic 中 audioUrl.isBlank() 的 true 臂
    // ---------------------------------------------------------------------
    @Test
    void generateMusic_audioUrlBlank_throwsRuntimeException() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider provider = mock(MediaProvider.class);
        when(repo.findById(1L)).thenReturn(Optional.of(provider));
        // 含 "minimax" -> matchMusic 返回 "minimaxmusicprovider"
        when(provider.getName()).thenReturn("MiniMax 音乐");
        when(provider.getApiKey()).thenReturn("k");
        when(provider.getApiAddress()).thenReturn("http://x");

        MusicProvider musicProvider = mock(MusicProvider.class);
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult(" ", 1));

        ByokGenerateService.DownloadSender sender = req -> {
            throw new AssertionError("不应走到下载");
        };

        ByokGenerateService service = new ByokGenerateService(
                repo, Map.of(), Map.of("minimaxmusicprovider", musicProvider), Map.of(),
                "./data/media", sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "MUSIC", 1L, "m", "p", Map.of());

        RuntimeException ex = assertThrows(RuntimeException.class, () -> service.generate(req));
        assertEquals("音乐生成失败：未返回产物地址", ex.getMessage());
    }

    // ---------------------------------------------------------------------
    // 用例 3：generateAvatar 中 status == FAILED 的 true 臂
    // ---------------------------------------------------------------------
    @Test
    void generateAvatar_remoteStatusFailed_throwsRuntimeExceptionWithBoom() {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider provider = mock(MediaProvider.class);
        when(repo.findById(1L)).thenReturn(Optional.of(provider));
        // 含 "did" -> matchAvatar 返回 "didavatarprovider"
        when(provider.getName()).thenReturn("D-ID 数字人");
        when(provider.getApiKey()).thenReturn("k");
        when(provider.getApiAddress()).thenReturn("http://x");

        AvatarProvider avatarProvider = mock(AvatarProvider.class);
        when(avatarProvider.submit(anyString(), anyString(), any(), any()))
                .thenReturn(new AvatarProvider.SubmitResult("t1"));
        when(avatarProvider.poll(anyString(), anyString()))
                .thenReturn(new AvatarProvider.PollResult(
                        AvatarProvider.RemoteStatus.FAILED, null, "boom", 0));

        ByokGenerateService.DownloadSender sender = req -> {
            throw new AssertionError("不应走到下载");
        };

        ByokGenerateService service = new ByokGenerateService(
                repo, Map.of(), Map.of(), Map.of("didavatarprovider", avatarProvider),
                "./data/media", sender);

        Map<String, String> options = Map.of(
                "imageUrl", "http://x/face.png",
                "audioUrl", "http://x/a.mp3");
        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "AVATAR", 1L, "m", "p", options);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> service.generate(req));
        assertEquals("数字人生成失败：boom", ex.getMessage());
    }

    // ---------------------------------------------------------------------
    // 用例 4：download 中 catch (IOException ignored) 臂
    //    HTTP 500 -> 进入 try (InputStream ignored = response.body())，
    //    body.close() 抛 IOException 被 catch 住，然后抛 HTTP 500 的 RuntimeException。
    // ---------------------------------------------------------------------
    @Test
    void download_httpError_closeThrowsIOException_caughtAndThrowsRuntimeException() throws IOException {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider provider = mock(MediaProvider.class);
        when(repo.findById(1L)).thenReturn(Optional.of(provider));
        when(provider.getName()).thenReturn("MiniMax 音乐");
        when(provider.getApiKey()).thenReturn("k");
        when(provider.getApiAddress()).thenReturn("http://x");

        MusicProvider musicProvider = mock(MusicProvider.class);
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("http://x/a.mp3", 1));

        InputStream body = mock(InputStream.class);
        // doAnswer 抛 IOException（受检异常不能 thenThrow）
        Mockito.doAnswer(inv -> {
            throw new IOException("drain-fail");
        }).when(body).close();

        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(500);
        when(response.body()).thenReturn(body);

        ByokGenerateService.DownloadSender sender = req -> response;

        ByokGenerateService service = new ByokGenerateService(
                repo, Map.of(), Map.of("minimaxmusicprovider", musicProvider), Map.of(),
                "./data/media", sender);

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "MUSIC", 1L, "m", "p", Map.of());

        RuntimeException ex = assertThrows(RuntimeException.class, () -> service.generate(req));
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains("产物下载失败，HTTP 500"),
                "实际消息：" + ex.getMessage());
    }

    // ---------------------------------------------------------------------
    // 用例 5 + 6：
    //   resolveExtension 第 373 行 slashIdx < 0 时取 path 臂
    //   registerAsset 第 422 行 assetService == null 提前返回臂
    //   走 generate MUSIC 公共路径：audioUrl="file.mp3"（无斜杠、无 query、无 fragment）。
    //   assetService 保持 null（不调用 setAssetService），若 registerAsset 未提前返回
    //   会 NPE，从而让用例失败——成功即证明该分支被走。
    // ---------------------------------------------------------------------
    @Test
    void resolveExtension_noSlash_takesWholePathAsLastSegment() throws Exception {
        // resolveExtension 为 private static：经 download() 公共路径无法触发无斜杠臂
        //（JDK HttpClient 要求 http/https URI 恒含 "://"），故反射直测。
        java.lang.reflect.Method m = ByokGenerateService.class.getDeclaredMethod(
                "resolveExtension", String.class, String.class);
        m.setAccessible(true);
        assertEquals("mp3", m.invoke(null, "file.mp3", "mp3"));
        // 对照：有斜杠走正常臂
        assertEquals("png", m.invoke(null, "http://x/a.png?token=1", "png"));
    }

    @Test
    void generateMusic_downloadSuccess_registerAssetNullAssetServiceEarlyReturn(
            @TempDir Path tempDir) {
        MediaProviderRepository repo = mock(MediaProviderRepository.class);
        MediaProvider provider = mock(MediaProvider.class);
        when(repo.findById(1L)).thenReturn(Optional.of(provider));
        when(provider.getName()).thenReturn("MiniMax 音乐");
        when(provider.getApiKey()).thenReturn("k");
        when(provider.getApiAddress()).thenReturn("http://x");

        MusicProvider musicProvider = mock(MusicProvider.class);
        when(musicProvider.generate(anyString(), anyString(), anyString(), anyString(), any(), anyBoolean()))
                .thenReturn(new MusicProvider.GenerateResult("http://x/a.mp3", 1));

        byte[] bytes = "fake-audio-bytes".getBytes(StandardCharsets.UTF_8);
        InputStream body = new ByteArrayInputStream(bytes);

        @SuppressWarnings("unchecked")
        HttpResponse<InputStream> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(200);
        when(response.body()).thenReturn(body);

        ByokGenerateService.DownloadSender sender = req -> response;

        ByokGenerateService service = new ByokGenerateService(
                repo, Map.of(), Map.of("minimaxmusicprovider", musicProvider), Map.of(),
                tempDir.toString(), sender);
        // 故意不调用 setAssetService，assetService 保持 null → registerAsset 第 422 行提前返回臂

        ByokGenerateService.GenerateRequest req = new ByokGenerateService.GenerateRequest(
                "MUSIC", 1L, "m", "p", Map.of());

        ByokGenerateService.GenerateResponse resp = service.generate(req);

        assertEquals("SUCCEEDED", resp.status());
        assertNotNull(resp.url());
        assertTrue(resp.url().startsWith("/api/byok/file/music/"),
                "实际 url：" + resp.url());
    }

    }
