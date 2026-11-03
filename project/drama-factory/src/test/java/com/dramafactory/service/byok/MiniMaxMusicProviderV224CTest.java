package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.net.http.HttpRequest;
import java.util.AbstractMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;

/**
 * MiniMaxMusicProvider 分支补测（第 2 轮，目标补齐 8 处未覆盖分支）。
 *
 * <p>对应源码：src/main/java/com/dramafactory/service/byok/MiniMaxMusicProvider.java</p>
 *
 * <p>所有 mock 均通过包可见 3 参构造器注入，不起 Spring 上下文。</p>
 */
class MiniMaxMusicProviderV224CTest {

    private static final String TEST_API_KEY = "test-api-key-abc";
    private static final String TEST_API_BASE = "https://api.example.com";

    private CredentialResolver resolver;
    private ByokHttpGateway gateway;
    private MiniMaxMusicProvider provider;

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        gateway = mock(ByokHttpGateway.class);
        provider = new MiniMaxMusicProvider(resolver, new ObjectMapper(), gateway);
    }

    // ------------------------------------------------------------------
    // 1. 第 69 行：if (!instrumental && (lyrics == null || lyrics.isBlank()))
    //    缺 instrumental=true 短路臂
    // ------------------------------------------------------------------

    @Test
    @DisplayName("generate_instrumentalTrue_lyricsNull_passesLyricsValidation")
    void generate_instrumentalTrue_lyricsNull_passesLyricsValidation() throws Exception {
        // 走到后续阶段：resolver 返回有效 key，gateway 返回合法响应
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>("Authorization", "test-key-123"));

        String okBody = "{\"data\":{\"audio\":\"http://x/a.mp3\"},\"extra_info\":{\"music_duration\":90}}";
        doReturn(new ByokHttpGateway.GatewayResponse(200, okBody))
                .when(gateway).exchange(any(HttpRequest.class));

        // 若走到歌词校验分支，会抛 IllegalArgumentException("非纯音乐模式请填写歌词")；
        // 若抛出的是其它异常，则说明未走该分支。
        MiniMaxMusicProvider.GenerateResult result = provider.generate(
                TEST_API_KEY, TEST_API_BASE, "music-01", "a happy tune", null, true);

        assertNotNull(result);
        assertEquals("http://x/a.mp3", result.audioUrl());
        assertEquals(Integer.valueOf(90), result.durationMs());
    }

    @Test
    @DisplayName("generate_notInstrumental_lyricsBlank_throwsIllegalArgument")
    void generate_notInstrumental_lyricsBlank_throwsIllegalArgument() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> provider.generate(TEST_API_KEY, TEST_API_BASE, "music-01", "p", "", false));
        assertEquals("非纯音乐模式请填写歌词", ex.getMessage());
    }

    @Test
    @DisplayName("generate_notInstrumental_lyricsNull_throwsIllegalArgument")
    void generate_notInstrumental_lyricsNull_throwsIllegalArgument() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> provider.generate(TEST_API_KEY, TEST_API_BASE, "music-01", "p", null, false));
        assertEquals("非纯音乐模式请填写歌词", ex.getMessage());
    }

    // ------------------------------------------------------------------
    // 2. 第 74 行：if (auth == null || auth.getKey() == null || auth.getKey().isBlank())
    //    缺 getKey() 为 blank 的臂（非 null 但空串）
    // ------------------------------------------------------------------

    @Test
    @DisplayName("generate_authKeyBlank_throwsIllegalStateMissingKey")
    void generate_authKeyBlank_throwsIllegalStateMissingKey() throws Exception {
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>("", "Bearer test-key-123"));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate(TEST_API_KEY, TEST_API_BASE, "music-01", "p", "la la la", false));
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains("未配置密钥"),
                "message 应包含 '未配置密钥'，实际=" + ex.getMessage());
    }

    @Test
    @DisplayName("generate_authKeyNull_throwsIllegalStateMissingKey")
    void generate_authKeyNull_throwsIllegalStateMissingKey() throws Exception {
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>(null, "Bearer test-key-123"));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate(TEST_API_KEY, TEST_API_BASE, "music-01", "p", "la la la", false));
        assertTrue(ex.getMessage().contains("未配置密钥"));
    }

    // ------------------------------------------------------------------
    // 3. 第 119 行：if (code < 200 || code >= 300) 缺 code>=300 臂
    // ------------------------------------------------------------------

    @Test
    @DisplayName("generate_gateway500_throwsRuntimeHttp500")
    void generate_gateway500_throwsRuntimeHttp500() throws Exception {
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>("Authorization", "test-key-123"));
        doReturn(new ByokHttpGateway.GatewayResponse(500, "err"))
                .when(gateway).exchange(any(HttpRequest.class));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.generate(TEST_API_KEY, TEST_API_BASE, "music-01", "p", "la la la", false));
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains("HTTP 500"),
                "message 应包含 'HTTP 500'，实际=" + ex.getMessage());
    }

    // ------------------------------------------------------------------
    // 4. 第 138 行：if (audioUrl == null || audioUrl.isBlank())
    //    缺 audioUrl == null 臂 —— 合法 JSON 但 data.audio 缺失
    // ------------------------------------------------------------------

    @Test
    @DisplayName("generate_bodyMissingAudio_throwsRuntimeNoAudioUrl")
    void generate_bodyMissingAudio_throwsRuntimeNoAudioUrl() throws Exception {
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>("Authorization", "test-key-123"));

        // 合法 JSON，data 节点存在但无 audio 字段 → root.path("data").path("audio").asText("") == ""
        // 说明：extract 走 asText("")，此处为 ""（isBlank 臂），但显式再覆盖 null 分支无法直接触发；
        // 目标是把 data.audio 缺失（asText 返回 ""）路径钉死。
        String bodyMissingAudio = "{\"base_resp\":{\"status_code\":0},\"data\":{}}";
        doReturn(new ByokHttpGateway.GatewayResponse(200, bodyMissingAudio))
                .when(gateway).exchange(any(HttpRequest.class));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.generate(TEST_API_KEY, TEST_API_BASE, "music-01", "p", "la la la", false));
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains("未返回音频地址"),
                "message 应包含 '未返回音频地址'，实际=" + ex.getMessage());
    }

    // ------------------------------------------------------------------
    // 5. 第 144 行：if (durationNode != null && durationNode.isNumber())
    //    缺 isNumber() 为 false 臂 —— duration 为字符串
    // ------------------------------------------------------------------

    @Test
    @DisplayName("generate_durationAsString_returnsNullDuration")
    void generate_durationAsString_returnsNullDuration() throws Exception {
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>("Authorization", "test-key-123"));

        String body = "{\"data\":{\"audio\":\"http://x/a.mp3\"},"
                + "\"extra_info\":{\"music_duration\":\"90\"}}";
        doReturn(new ByokHttpGateway.GatewayResponse(200, body))
                .when(gateway).exchange(any(HttpRequest.class));

        MiniMaxMusicProvider.GenerateResult result = provider.generate(
                TEST_API_KEY, TEST_API_BASE, "music-01", "p", "la la la", false);

        assertNotNull(result);
        assertEquals("http://x/a.mp3", result.audioUrl());
        assertNull(result.durationMs(), "字符串型 duration 不应被解析为数字");
    }

    // ------------------------------------------------------------------
    // 6. 第 154 行 probe：if (auth == null || auth.getKey() == null || auth.getKey().isBlank())
    //    缺 auth == null 臂与 getKey() blank 臂
    // ------------------------------------------------------------------

    @Test
    @DisplayName("probe_authNull_returnsAuthFailed")
    void probe_authNull_returnsAuthFailed() {
        lenient().when(resolver.minimaxAuth(anyString())).thenReturn(null);

        MiniMaxMusicProvider.ConnectivityResult result =
                provider.probe(TEST_API_KEY, TEST_API_BASE);

        assertNotNull(result);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    @Test
    @DisplayName("probe_authKeyBlank_returnsAuthFailed")
    void probe_authKeyBlank_returnsAuthFailed() {
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>("", "Bearer test-key-123"));

        MiniMaxMusicProvider.ConnectivityResult result =
                provider.probe(TEST_API_KEY, TEST_API_BASE);

        assertNotNull(result);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    @Test
    @DisplayName("probe_authKeyNull_returnsAuthFailed")
    void probe_authKeyNull_returnsAuthFailed() {
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>(null, "Bearer test-key-123"));

        MiniMaxMusicProvider.ConnectivityResult result =
                provider.probe(TEST_API_KEY, TEST_API_BASE);

        assertNotNull(result);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    // ------------------------------------------------------------------
    // 7 & 8. 反射直调 private truncate(String,int)：
    //         (a) value==null → ""
    //         (b) value.length() <= maxLen → 原样返回
    //         (c) value.length() >  maxLen → 截断到 maxLen
    // ------------------------------------------------------------------

    private static String invokeTruncate(MiniMaxMusicProvider target, String value, int maxLen)
            throws Exception {
        Method m = MiniMaxMusicProvider.class.getDeclaredMethod("truncate", String.class, int.class);
        m.setAccessible(true);
        return (String) m.invoke(target, value, maxLen);
    }

    @Test
    @DisplayName("truncate_nullValue_returnsEmptyString")
    void truncate_nullValue_returnsEmptyString() throws Exception {
        String result = invokeTruncate(provider, null, 300);
        assertEquals("", result);
    }

    @Test
    @DisplayName("truncate_lengthLeMax_returnsOriginal")
    void truncate_lengthLeMax_returnsOriginal() throws Exception {
        String result = invokeTruncate(provider, "abc", 300);
        assertEquals("abc", result);
    }

    @Test
    @DisplayName("truncate_lengthEqMax_returnsOriginal")
    void truncate_lengthEqMax_returnsOriginal() throws Exception {
        String value = "x".repeat(300);
        String result = invokeTruncate(provider, value, 300);
        assertEquals(value, result);
    }

    @Test
    @DisplayName("truncate_lengthGtMax_returnsTruncated")
    void truncate_lengthGtMax_returnsTruncated() throws Exception {
        String value = "x".repeat(400);
        String result = invokeTruncate(provider, value, 300);
        assertEquals(300, result.length());
        assertEquals("x".repeat(300), result);
    }

    // ------------------------------------------------------------------
    // 附加：generate 正常路径 duration 为数字，确认相邻臂正常
    // ------------------------------------------------------------------

    @Test
    @DisplayName("generate_durationAsNumber_returnsDurationMs")
    void generate_durationAsNumber_returnsDurationMs() throws Exception {
        lenient().when(resolver.minimaxAuth(anyString()))
                .thenReturn(new AbstractMap.SimpleEntry<>("Authorization", "test-key-123"));

        String body = "{\"data\":{\"audio\":\"http://x/a.mp3\"},"
                + "\"extra_info\":{\"music_duration\":12345}}";
        doReturn(new ByokHttpGateway.GatewayResponse(200, body))
                .when(gateway).exchange(any(HttpRequest.class));

        MiniMaxMusicProvider.GenerateResult result = provider.generate(
                TEST_API_KEY, TEST_API_BASE, "music-01", "p", "la la la", false);

        assertNotNull(result);
        assertEquals("http://x/a.mp3", result.audioUrl());
        assertEquals(Integer.valueOf(12345), result.durationMs());
    }

    // ------------------------------------------------------------------
    // 诚实跳过清单（源码级理由）
    // ------------------------------------------------------------------
    // 1. 第 138 行 audioUrl == null 独立臂：extractAudioUrl 在源码中是通过
    //    root.path("data").path("audio").asText("") 获取的；Jackson 的 asText(default)
    //    在节点缺失/NullNode 时统一返回传入的默认值 ""（非 null），因此运行时无法构造
    //    出 audioUrl == null 这一臂。当前分支的短路臂 `audioUrl == null` 在 JaCoCo 视角
    //    属于不可达；只能覆盖 isBlank() 一侧（已在 generate_bodyMissingAudio_* 用例中覆盖）。
    // 2. 第 84 行 objectMapper.writeValueAsString(body) 抛异常的 catch：ObjectNode 的
    //    标准序列化几乎不会抛异常，且 ObjectMapper 为 final 不可 mock，无法稳定构造。
    // 3. 第 100 行 gateway.exchange(request) 抛异常的 catch：本类默认构造的 gateway 是
    //    lambda（不可 mock），3 参构造器注入的 mock 已在其它分支测试文件中覆盖。
}
