package com.dramafactory.service.byok;

import com.dramafactory.service.byok.MusicProvider.GenerateResult;
import com.dramafactory.service.video.VideoProvider;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * v2.20 第 D 批：AceStepMusicProvider 剩余未覆盖分支补充测试。
 *
 * <p>诚实跳过说明：probe 中 {@code objectMapper.writeValueAsString(body)} 抛异常的臂（源码 120-123 行）
 * 无法在本测试中触发——{@code objectMapper} 是 {@code private final} 字段且无 setter/构造注入点，
 * 探针 body 恒为固定的简单 Map（String/Boolean 值），Jackson 不会对其实例化抛异常。
 * 故该臂不构造硬造测试，仅在此注明。
 */
class AceStepMusicProviderV220DTest {

    private HttpServer server;
    private String base;
    private final AtomicReference<Integer> nextStatus = new AtomicReference<>(200);
    private final AtomicReference<String> nextBody = new AtomicReference<>("{}");

    private AceStepMusicProvider provider;

    @BeforeEach
    void setUp() throws Exception {
        server = HttpServer.create(new InetSocketAddress("::1", 0), 0);
        server.createContext("/", exchange -> {
            byte[] req = exchange.getRequestBody().readAllBytes();
            Integer status = nextStatus.get();
            String body = nextBody.get();
            byte[] resp = body == null ? new byte[0] : body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, resp.length);
            exchange.getResponseBody().write(resp);
            exchange.close();
            // 保留 req 引用避免被优化掉（本地假服务器，无副作用）
            if (req.length < 0) {
                throw new IllegalStateException();
            }
        });
        server.start();
        base = "http://[::1]:" + server.getAddress().getPort();
        provider = new AceStepMusicProvider();
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    private void preset(int status, String body) {
        nextStatus.set(status);
        nextBody.set(body);
    }

    // ---------------- generate：prompt == null 走空字符串臂（源码 55 行） ----------------

    @Test
    void generate_nullPrompt_usesEmptyStringInBody() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\"}}");
        GenerateResult result = provider.generate("k", base, "ace-step", null, "歌词", false);
        assertNotNull(result);
        assertEquals("http://x/a.mp3", result.audioUrl());
    }

    // ---------------- generate：lyrics == null 且非纯音乐走空字符串臂（源码 56 行） ----------------

    @Test
    void generate_nullLyricsNonInstrumental_usesEmptyStringInBody() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/b.mp3\"}}");
        GenerateResult result = provider.generate("k", base, "ace-step", "p", null, false);
        assertNotNull(result);
        assertEquals("http://x/b.mp3", result.audioUrl());
    }

    // ---------------- generate：response.body() 为空走空字符串臂（源码 83 行） ----------------
    // 本地 HttpServer 无法直接返回 null body；2xx + 空体 -> responseBody 为空串。
    // 注意 Jackson 2.17 的 readTree("") 返回 MissingNode 不抛异常，因此走的是
    // extractAudioUrl 返回 null -> "作曲接口未返回音频地址"臂。

    @Test
    void generate_emptyResponseBody_throwsMissingAudioUrl() {
        preset(200, null);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "ace-step", "p", "l", false));
        assertTrue(ex.getMessage().startsWith("作曲接口未返回音频地址："));
    }

    // 诚实跳过：generate 的 code < 200 臂。JDK HttpServer 发 199 会被
    // java.net.http.HttpClient 当作 1xx interim 等待最终响应（实测 40 秒超时），
    // 真实服务端不会返回最终态 <200 状态码，该防御分支走本地 HttpServer 无法触发。

    // ---------------- extractAudioUrl：data 非 object，顶层 audio_url 为 blank（源码 176-179 行） ----------------
    // data 是数组（非 object），跳过 data 内分支；顶层 audio_url 为空白文本，最终返回 null。

    @Test
    void generate_dataNotObject_topAudioUrlBlank_throwsMissingAudioUrl() {
        preset(200, "{\"data\":[],\"audio_url\":\"   \"}");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "ace-step", "p", "l", false));
        assertTrue(ex.getMessage().startsWith("作曲接口未返回音频地址："));
    }

    // ---------------- extractAudioUrl：data 是 object，audio_url 非文本，url 缺失，顶层缺失（源码 167-180 行） ----------------
    // data.audio_url 为数值（isTextual false），data.url 缺失（isTextual false），顶层 audio_url 缺失 -> null。

    @Test
    void generate_dataAudioUrlNonTextualAndNoUrl_topMissing_throwsMissingAudioUrl() {
        preset(200, "{\"data\":{\"audio_url\":123}}");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "ace-step", "p", "l", false));
        assertTrue(ex.getMessage().startsWith("作曲接口未返回音频地址："));
    }

    // ---------------- extractAudioUrl：data.url 为空白文本臂（源码 171-173 行） ----------------
    // data.audio_url 缺失，data.url 为空白文本 -> 跳过，顶层缺失 -> null。

    @Test
    void generate_dataUrlBlankText_topMissing_throwsMissingAudioUrl() {
        preset(200, "{\"data\":{\"url\":\"  \"}}");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "ace-step", "p", "l", false));
        assertTrue(ex.getMessage().startsWith("作曲接口未返回音频地址："));
    }

    // ---------------- extractAudioUrl：data.audio_url 为空白文本臂（源码 168 行） ----------------
    // data.audio_url 为空白文本 -> 跳过；data.url 为有效文本 -> 返回 data.url。

    @Test
    void generate_dataAudioUrlBlank_fallsToDataUrl() {
        preset(200, "{\"data\":{\"audio_url\":\"  \",\"url\":\"http://x/c.mp3\"}}");
        GenerateResult result = provider.generate("k", base, "ace-step", "p", "l", false);
        assertEquals("http://x/c.mp3", result.audioUrl());
    }

    // ---------------- normalizeBase：apiBase 为空白（isBlank）走抛异常臂（源码 207 行） ----------------

    @Test
    void generate_blankApiBase_throwsNormalizeBase() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", "   ", "ace-step", "p", "l", false));
        assertEquals("未配置 API 地址：请先在通道管理填写该供应商的 API Base", ex.getMessage());
    }

    @Test
    void probe_blankApiBase_throwsNormalizeBase() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.probe("k", "   "));
        assertEquals("未配置 API 地址：请先在通道管理填写该供应商的 API Base", ex.getMessage());
    }

    // ---------------- extractDurationMs：data 非 object 走顶层 duration 分支（源码 185/199-202 行） ----------------
    // data 是数组（非 object），顶层 duration 为数值 -> 走顶层秒转毫秒臂。

    @Test
    void generate_dataNotObject_topLevelDurationSeconds() {
        preset(200, "{\"data\":[],\"audio_url\":\"http://x/d.mp3\",\"duration\":2.0}");
        GenerateResult result = provider.generate("k", base, "ace-step", "p", "l", false);
        assertEquals("http://x/d.mp3", result.audioUrl());
        assertEquals(2000, result.durationMs());
    }

    // ---------------- extractDurationMs：data.audio_url 有效但 duration 全缺失 -> null（源码 203 行） ----------------

    @Test
    void generate_durationAbsentOnBothLevels_returnsNullDuration() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/e.mp3\"}}");
        GenerateResult result = provider.generate("k", base, "ace-step", "p", "l", false);
        assertEquals("http://x/e.mp3", result.audioUrl());
        assertNull(result.durationMs());
    }

    // ---------------- probe：code >= 400 且 < 500（非 401/403/429）走 OK 分支（源码 156-158 行） ----------------

    @Test
    void probe_other4xxBelowBoundary_returnsOk() {
        preset(400, "bad");
        MusicProvider.ConnectivityResult result = provider.probe("k", base);
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
        assertTrue(result.detail().contains("HTTP 400"));
    }

    // ---------------- probe：2xx 成功（覆盖 200 下界与 <300 上界） ----------------

    @Test
    void probe_2xxLowerBound_returnsOk() {
        preset(200, "{}");
        MusicProvider.ConnectivityResult result = provider.probe("k", base);
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
        assertTrue(result.detail().contains("HTTP 200"));
    }
}
